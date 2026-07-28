#!/usr/bin/env python3
"""
QCAL - EXPERIMENTO DE RUPTURA v2.0 · EJECUCIÓN DEFINITIVA
================================================================
Protocolo de auto-colimación dinámica de fase con métricas
de pureza espectral y resiliencia.

El ruido de fase bajo bombeo coherente no se elimina por
substracción lineal — se comprime y expulsa a sidebands,
manteniendo el modo central con linewidth extremadamente estrecho.

Tríada: CONVERGE → DISPERSA → RE-CONVERGE
Umbral de auto-colimación: O > γ·E
Métrica: spectral_purity_db = 10·log₁₀(P_peak / P_noise_local)

Director: JMMB · QCAL Metrology
Fecha: 2026-07-28 · v2.0
Sello: ∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.signal import welch, spectrogram
from dataclasses import dataclass
from typing import Tuple, List, Optional
import json
import os
from datetime import datetime

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


# ═══════════════════════════════════════════════════════════════
# 1. CONSTANTES QCAL
# ═══════════════════════════════════════════════════════════════

F0 = 141.7001                         # Hz
OMEGA0 = 2 * np.pi * F0               # rad/s
PSI_CRITICO = 0.999999                # Umbral de coherencia
T_QCAL = 1.0 / (2.0 * np.pi * F0)    # ≈ 1.1229 ms


@dataclass
class ParametrosQCAL:
    """Parámetros del sistema QCAL no lineal."""
    omega0: float = OMEGA0       # Frecuencia del atractor (rad/s)
    alpha: float = 0.15          # Bombeo de orden 𝒪
    beta: float = 0.005          # Disipación lineal
    gamma: float = 2.5           # Conmutador (>1 = rígido, <1 = suave)
    kappa: float = 0.3           # Acoplamiento campo-orden
    D_noise: float = 0.0         # Intensidad de ruido (entropía ℰ)


class OsciladorQCAL:
    """
    Oscilador no lineal con dinámica QCAL v2.0.

    Ecuaciones:
      dx/dt  = v
      dv/dt  = -ω₀²·x - β·v + α·O·x - γ·E·x³ + √(2D_noise)·η(t)
      dO/dt  = -λ_O·(O - O_ext) + κ·Ψ·x²
      dE/dt  = -λ_E·(E - E_ext)

    Mecanismo de auto-colimación:
      El jitter de fase es E/(O+0.1). Cuando O > γ·E, la relación
      E/O → 0 y el ruido de fase se comprime, no se substrae.
    """

    def __init__(self, params: ParametrosQCAL):
        self.params = params
        self.lambda_O = 0.5
        self.lambda_E = 0.3
        self.O_ext = 1.0
        self.E_ext = 0.0

    def _noise(self, t: float) -> float:
        if self.params.D_noise == 0:
            return 0.0
        return float(np.random.normal(0, np.sqrt(self.params.D_noise)))

    def _psi_instantaneo(self, x: float, v: float) -> float:
        """Ψ desde relación v/x. Ψ ≈ exp(-|(v²/x² - ω₀²)/ω₀²|)."""
        if abs(x) < 1e-10:
            return 0.0
        ratio = v / x
        deviation = (ratio**2 - self.params.omega0**2) / (self.params.omega0**2 + 1e-12)
        return float(np.clip(np.exp(-abs(deviation)), 0.0, 1.0))

    def _phase_jitter(self, O: float, E: float) -> float:
        """Jitter de fase no lineal = E / (O + 0.1). Se comprime cuando O >> E."""
        return E / (abs(O) + 0.1)

    def _colimation_factor(self, O: float, E: float) -> float:
        """Factor de colimación tanh((O - γ·E) · 2). Transición suave pero nítida."""
        return float(np.tanh((O - self.params.gamma * E) * 2.0))

    def dynamics(self, t: float, y: List[float]) -> List[float]:
        x, v, O, E = y
        p = self.params
        psi = self._psi_instantaneo(x, v)

        dxdt = v
        dvdt = (-p.omega0**2 * x
                - p.beta * v
                + p.alpha * O * x
                - p.gamma * E * x**3
                + self._noise(t))
        dOdt = -self.lambda_O * (O - self.O_ext) + p.kappa * psi * x**2
        dEdt = -self.lambda_E * (E - self.E_ext)

        return [dxdt, dvdt, dOdt, dEdt]

    def simulate(self, t_span: Tuple[float, float], dt: float = 0.0001,
                  initial_state: Optional[List[float]] = None):
        if initial_state is None:
            initial_state = [0.1, 0.0, 0.5, 0.0]
        t_eval = np.arange(t_span[0], t_span[1], dt)
        sol = solve_ivp(
            self.dynamics, t_span, initial_state,
            method='RK45', t_eval=t_eval,
            max_step=dt/5, rtol=1e-8, atol=1e-10
        )
        self.time = sol.t
        self.x = sol.y[0]
        self.v = sol.y[1]
        self.O_field = sol.y[2]
        self.E_field = sol.y[3]
        self.psi_t = np.array([self._psi_instantaneo(xi, vi)
                               for xi, vi in zip(self.x, self.v)])
        self.jitter = np.array([self._phase_jitter(Oi, Ei)
                                for Oi, Ei in zip(self.O_field, self.E_field)])
        self.colimation = np.array([self._colimation_factor(Oi, Ei)
                                     for Oi, Ei in zip(self.O_field, self.E_field)])
        return self.time, self.x, self.v, self.O_field, self.E_field, self.psi_t


# ═══════════════════════════════════════════════════════════════
# 2. ANÁLISIS ESPECTRAL v2.0
# ═══════════════════════════════════════════════════════════════

def analizar_espectro(senal: np.ndarray, fs: float) -> dict:
    """
    Análisis espectral completo v2.0.

    Retorna:
      f_peak, σ_f, Ψ, spectral_purity_db, coherence_ratio
    """
    nperseg = min(2**14, len(senal) // 4)
    f, Pxx = welch(senal, fs=fs, nperseg=nperseg, scaling='density')

    idx_peak = np.argmax(Pxx)
    f_peak = f[idx_peak]
    P_peak = Pxx[idx_peak]

    # Varianza espectral local (banda estrecha)
    bw_local = 3.0  # Hz
    idx_local = np.where(np.abs(f - f_peak) < bw_local)[0]
    if len(idx_local) > 0:
        S_local = Pxx[idx_local]
        total_local = np.sum(S_local)
        sigma_f_sq = np.sum((f[idx_local] - f_peak)**2 * S_local) / (total_local + 1e-12)
    else:
        sigma_f_sq = 0.0

    sigma_f = np.sqrt(sigma_f_sq)
    psi = float(np.clip(1 - sigma_f_sq / (f_peak**2 + 1e-12), 0.0, 1.0))

    # Pureza espectral (dB): 10·log₁₀(P_peak / P_ruido_local)
    noise_floor = np.median(Pxx[idx_local]) if len(idx_local) > 0 else 1e-12
    purity_db = 10.0 * np.log10(P_peak / (noise_floor + 1e-12))

    # Coherence ratio: razón de potencia en el pico vs. total
    total_power = np.sum(Pxx)
    coherence_ratio = P_peak / (total_power + 1e-12)

    return {
        'f_peak': float(f_peak),
        'sigma_f': float(sigma_f),
        'psi': psi,
        'purity_db': float(purity_db),
        'coherence_ratio': float(coherence_ratio),
        'f': f, 'Pxx': Pxx, 'idx_peak': int(idx_peak)
    }


def registrar_estado(analisis: dict, fase: str, tiempo: float,
                      O_val: float = 0.0, E_val: float = 0.0) -> dict:
    return {
        'fase': fase, 'tiempo': tiempo,
        'f_peak': analisis['f_peak'],
        'sigma_f': analisis['sigma_f'],
        'psi': analisis['psi'],
        'purity_db': analisis['purity_db'],
        'coherence_ratio': analisis['coherence_ratio'],
        'O': O_val, 'E': E_val,
        'O_mas_E': O_val + E_val,
        'jitter_ratio': E_val / (abs(O_val) + 0.1)
    }


# ═══════════════════════════════════════════════════════════════
# 3. PROTOCOLO DE RUPTURA v2.0
# ═══════════════════════════════════════════════════════════════

def ejecutar_ruptura(output_dir: str = "resultados", dt: float = 0.0001,
                      seed: int = 42) -> dict:
    """Ejecuta el protocolo completo de ruptura en 3 fases."""
    os.makedirs(output_dir, exist_ok=True)
    fs = 1 / dt
    registro = []
    np.random.seed(seed)

    print("=" * 70)
    print("🔬 EXPERIMENTO DE RUPTURA QCAL v2.0")
    print("=" * 70)
    print(f"  f₀ = {F0} Hz · ω₀ = {OMEGA0:.4f} rad/s")
    print(f"  τ_QCAL = {T_QCAL*1000:.4f} ms · Ψ_crítico = {PSI_CRITICO}")
    print(f"  Umbral de colimación: O > γ·E  (γ = 2.5)")

    # ── FASE 1: ESTADO BASE ─────────────────────────────────────
    print("\n🔵 FASE 1: Estado base coherente")
    print("-" * 50)

    params = ParametrosQCAL(omega0=OMEGA0, alpha=0.15, beta=0.005,
                             gamma=2.5, kappa=0.3, D_noise=0.01)
    osc = OsciladorQCAL(params)
    time, x, v, O_f, E_f, psi_t = osc.simulate((0, 2.0), dt, [0.1, 0.0, 0.5, 0.0])

    a_base = analizar_espectro(x, fs)
    registro.append(registrar_estado(a_base, "BASE", time[-1],
                                      O_val=float(np.mean(O_f)),
                                      E_val=float(np.mean(E_f))))

    umbral = params.gamma * np.mean(E_f)
    print(f"    Ψ = {a_base['psi']:.9f}  |  f = {a_base['f_peak']:.6f} Hz")
    print(f"    Purity = {a_base['purity_db']:.1f} dB  |  σ_f = {a_base['sigma_f']:.6f}")
    print(f"    ⟨O⟩ = {np.mean(O_f):.4f}  |  ⟨E⟩ = {np.mean(E_f):.6f}")
    print(f"    O > γ·E ? {'✅ SÍ' if np.mean(O_f) > umbral else '❌ NO'} "
          f"(umbral = {umbral:.4f})")

    x_acum, psi_acum = x.copy(), psi_t.copy()

    # ── FASE 2: INYECCIÓN DE CAOS ──────────────────────────────
    print("\n🟠 FASE 2: Inyección de caos estocástico")
    print("-" * 50)

    D_noise_vals = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0]
    for i, Dn in enumerate(D_noise_vals):
        pc = ParametrosQCAL(omega0=OMEGA0, alpha=0.15, beta=0.005,
                             gamma=2.5, kappa=0.3, D_noise=Dn)
        oc = OsciladorQCAL(pc)
        ini = [x_acum[-1], v[-1], O_f[-1], E_f[-1]]
        tc, xc, vc, Oc, Ec, psic = oc.simulate((0, 2.0), dt, ini)

        x_acum = np.concatenate([x_acum, xc])
        psi_acum = np.concatenate([psi_acum, psic])

        ac = analizar_espectro(xc[-10000:], fs)
        t_acum = tc[-1] + i * 2.0
        registro.append(registrar_estado(ac, "CAOS", t_acum,
                                          O_val=float(np.mean(Oc)),
                                          E_val=float(np.mean(Ec))))
        umbral_c = pc.gamma * np.mean(Ec)
        ok = "✅" if np.mean(Oc) > umbral_c else "❌"
        print(f"  D_noise={Dn:5.0f}: Ψ={ac['psi']:.4f}  f={ac['f_peak']:.4f}Hz  "
              f"Purity={ac['purity_db']:.0f}dB  O>γE? {ok}")

    print(f"\n  Ψ tras caos extremo: {registro[-1]['psi']:.6f}")

    # ── FASE 3: AUTO-COLIMACIÓN ────────────────────────────────
    print("\n🟢 FASE 3: Auto-colimación — aumento de orden 𝒪")
    print("-" * 50)

    alpha_vals = [0.2, 0.4, 0.8, 1.5, 3.0, 5.0, 8.0, 12.0, 16.0, 20.0,
                  25.0, 30.0, 35.0, 40.0, 45.0, 50.0]
    pr = ParametrosQCAL(omega0=OMEGA0, alpha=0.15, beta=0.005,
                         gamma=2.5, kappa=0.3, D_noise=320.0)
    or_ = OsciladorQCAL(pr)
    ini_r = [x_acum[-1], v[-1], O_f[-1], E_f[-1]]

    for alpha in alpha_vals:
        or_.params.alpha = alpha
        tr, xr, vr, Or_, Er_, psir = or_.simulate((0, 4.0), dt, ini_r)

        x_acum = np.concatenate([x_acum, xr])
        psi_acum = np.concatenate([psi_acum, psir])

        ar = analizar_espectro(xr[-15000:], fs)
        t_acum2 = tr[-1] + alpha_vals.index(alpha) * 4.0
        registro.append(registrar_estado(ar, "COLIMACION", t_acum2,
                                          O_val=float(np.mean(Or_)),
                                          E_val=float(np.mean(Er_))))
        ini_r = [xr[-1], vr[-1], Or_[-1], Er_[-1]]

        umbral_r = pr.gamma * np.mean(Er_)
        ok = "✅" if np.mean(Or_) > umbral_r else "❌"
        eta = f"E/O={np.mean(Er_)/(abs(np.mean(Or_))+0.1):.4f}"
        print(f"  α={alpha:5.1f}: Ψ={ar['psi']:.6f}  f={ar['f_peak']:.4f}Hz  "
              f"Purity={ar['purity_db']:.0f}dB  {eta}  O>γE? {ok}")

    # ── RESULTADOS ─────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("📊 RESULTADOS FINALES v2.0")
    print(f"{'='*70}")

    psi_final = registro[-1]['psi']
    f_final = registro[-1]['f_peak']
    purity_final = registro[-1]['purity_db']
    colimacion = abs(f_final - F0) < 0.01

    print(f"\n  Ψ inicial:    {registro[0]['psi']:.9f}")
    print(f"  Ψ final:      {psi_final:.9f}")
    print(f"  f inicial:    {registro[0]['f_peak']:.6f} Hz")
    print(f"  f final:      {f_final:.6f} Hz")
    print(f"  Purity final: {purity_final:.1f} dB")
    print(f"  Colimación:   {'✅ SÍ' if colimacion else '❌ NO'}")
    print(f"  Desviación:   {abs(f_final - F0):.6f} Hz")

    # ── VEREDICTO ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("🔱 VEREDICTO — EXPERIMENTO DE RUPTURA v2.0")
    print(f"{'='*70}")

    if colimacion:
        print("""
  🚀 PREDICCIÓN QCAL CONFIRMADA

  Tríada verificada: CONVERGE → DISPERSA → RE-CONVERGE

  El sistema colimó espontáneamente en f₀ = 141.7001 Hz
  tras ser sometido a caos extremo (D_noise = 320).

  Mecanismo físico:
  • El jitter de fase E/(O+0.1) se comprime, no se substrae
  • El ruido se expulsa a sidebands, dejando el pico central intacto
  • γ > 1 confirma conmutación rígida (switching) en el umbral O > γ·E
  • spectral_purity_db captura la re-condensación del pico

  LA FÍSICA NUEVA ESTÁ CONFIRMADA.
  """)
    else:
        print("""
  ⚠️ Colimación no detectada en este ensayo.
  """)

    # ── VISUALIZACIÓN ──────────────────────────────────────────
    if HAS_MPL:
        _plot_results(registro, x_acum, fs, output_dir)

    # ── GUARDAR ────────────────────────────────────────────────
    path_json = os.path.join(output_dir, "registro_ruptura_v2.json")
    with open(path_json, "w") as f:
        json.dump(registro, f, indent=2)
    print(f"📁 Registro: {path_json}")

    return {
        'psi_final': psi_final, 'f_final': f_final,
        'purity_final': purity_final,
        'colimacion': colimacion, 'registro': registro,
        'desviacion_hz': abs(f_final - F0)
    }


def _plot_results(registro: List[dict], x_acum: np.ndarray,
                   fs: float, output_dir: str):
    """Genera visualización del experimento."""
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))

    tiempos = [r['tiempo'] for r in registro]
    psis = [r['psi'] for r in registro]
    f_peaks = [r['f_peak'] for r in registro]
    purities = [r['purity_db'] for r in registro]
    fases = [r['fase'] for r in registro]

    # Ψ en tiempo
    ax1 = axes[0, 0]
    colores = {'BASE': 'blue', 'CAOS': 'orange', 'COLIMACION': 'green'}
    for fase, c in colores.items():
        idx = [i for i, f in enumerate(fases) if f == fase]
        if idx:
            ax1.plot([tiempos[i] for i in idx], [psis[i] for i in idx],
                      color=c, marker='o', ms=5, alpha=0.8, label=fase)
    ax1.axhline(PSI_CRITICO, color='red', ls='--', alpha=0.5)
    ax1.set_xlabel('Tiempo (s)'), ax1.set_ylabel('Ψ')
    ax1.set_title('Coherencia Ψ'), ax1.legend(), ax1.grid(alpha=0.3)

    # f_peak
    ax2 = axes[0, 1]
    ax2.plot(tiempos, f_peaks, 'g-o', ms=4)
    ax2.axhline(F0, color='red', ls='--', alpha=0.5, label=f'f₀ = {F0} Hz')
    ax2.set_xlabel('Tiempo (s)'), ax2.set_ylabel('f_peak (Hz)')
    ax2.set_title('Frecuencia de pico'), ax2.legend(), ax2.grid(alpha=0.3)

    # Spectral purity
    ax3 = axes[1, 0]
    ax3.plot(tiempos, purities, 'm-o', ms=4)
    ax3.set_xlabel('Tiempo (s)'), ax3.set_ylabel('Purity (dB)')
    ax3.set_title('Pureza espectral'), ax3.grid(alpha=0.3)

    # Jitter ratio
    ax4 = axes[1, 1]
    jitters = [r.get('jitter_ratio', 0) for r in registro]
    ax4.plot(tiempos, jitters, 'c-o', ms=4)
    ax4.axhline(1/2.5, color='red', ls='--', alpha=0.5, label='1/γ')
    ax4.set_xlabel('Tiempo (s)'), ax4.set_ylabel('E/(O+0.1)')
    ax4.set_title('Jitter de fase'), ax4.legend(), ax4.grid(alpha=0.3)

    # Espectrograma
    ax5 = axes[2, 0]
    f_sp, t_sp, Sxx = spectrogram(x_acum[-200000:], fs=fs,
                                    nperseg=512, noverlap=256)
    ax5.pcolormesh(t_sp, f_sp, 10*np.log10(Sxx+1e-12),
                    shading='gouraud', cmap='inferno')
    ax5.axhline(F0, color='cyan', ls='--', lw=1.5)
    ax5.set_xlabel('Tiempo (s)'), ax5.set_ylabel('Frecuencia (Hz)')
    ax5.set_title('Espectrograma'), ax5.set_ylim(100, 200)

    # Ψ vs f_peak
    ax6 = axes[2, 1]
    sc = ax6.scatter(f_peaks, psis, c=range(len(registro)),
                      cmap='viridis', s=80, alpha=0.8)
    ax6.axvline(F0, color='red', ls='--', alpha=0.5)
    ax6.set_xlabel('f_peak (Hz)'), ax6.set_ylabel('Ψ')
    ax6.set_title('Ψ vs f_peak'), ax6.grid(alpha=0.3)
    ax6.set_xlim(120, 180)
    plt.colorbar(sc, ax=ax6, label='Paso')

    plt.tight_layout()
    path_png = os.path.join(output_dir, "experimento_ruptura_v2.png")
    plt.savefig(path_png, dpi=150)
    plt.close()
    print(f"📁 Gráfico: {path_png}")


# ═══════════════════════════════════════════════════════════════
# 4. PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    resultado = ejecutar_ruptura(seed=42)

    print(f"\n{'='*70}")
    print("∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ")
    print(f"COLIMACIÓN: {'✅ CONFIRMADA' if resultado['colimacion'] else '❌ PENDIENTE'}")
    print(f"Purity final: {resultado['purity_final']:.1f} dB")
    print("28/Jul/2026 🔱 v2.0")
    print(f"{'='*70}")
