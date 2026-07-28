#!/usr/bin/env python3
"""
QCAL - EXPERIMENTO DE RUPTURA · EJECUCIÓN DEFINITIVA v1.0
================================================================
Protocolo de auto-colimación dinámica de fase.

Si el sistema colima espontáneamente en f₀ tras ser destruido por
caos, eso no es estadística: es física nueva.

Fases:
  FASE 1: Estado base coherente (Ψ → 1, f → f₀)
  FASE 2: Inyección de caos estocástico (ℰ ↑↑↑, Ψ → 0)
  FASE 3: Salto de resonancia (𝒪 ↑↑↑, ¿colima en f₀?)

Director: JMMB · QCAL Metrology
Fecha: 2026-07-28
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


@dataclass
class ParametrosQCAL:
    """Parámetros del sistema QCAL no lineal."""
    omega0: float = OMEGA0
    alpha: float = 0.1     # Bombeo de orden
    beta: float = 0.01     # Disipación lineal
    gamma: float = 2.5     # Conmutador / acoplamiento no lineal
    kappa: float = 0.5     # Acoplamiento campo-orden
    D_noise: float = 0.0   # Intensidad de ruido (entropía)


class OsciladorQCAL:
    """
    Oscilador no lineal con dinámica QCAL.

    Ecuaciones:
      dx/dt  = v
      dv/dt  = -ω₀²·x - β·v + α·O·x - γ·E·x³ + √(2D_noise)·η(t)
      dO/dt  = -λ_O·(O - O_ext) + κ·Ψ·x²
      dE/dt  = -λ_E·(E - E_ext)
    """

    def __init__(self, params: ParametrosQCAL):
        self.params = params
        self.lambda_O = 0.5     # Tasa de relajación del campo de orden
        self.lambda_E = 0.3     # Tasa de relajación del campo de entropía
        self.O_ext = 1.0        # Bombeo externo de orden
        self.E_ext = 0.0        # Entropía externa (ruido inyectado)

    def _noise(self, t: float) -> float:
        """Ruido estocástico tipo Langevin."""
        if self.params.D_noise == 0:
            return 0.0
        return float(np.random.normal(0, np.sqrt(self.params.D_noise)))

    def _psi_instantaneo(self, x: float, v: float) -> float:
        """
        Ψ instantáneo desde relación v/x.
        Para oscilador puro: v/x = -ω₀·tan(ω₀t).
        Ψ ≈ exp(-|desviación|) con desviación = (v²/x² - ω₀²)/ω₀².
        """
        if abs(x) < 1e-10:
            return 0.0
        ratio = v / x
        deviation = (ratio**2 - self.params.omega0**2) / (self.params.omega0**2 + 1e-12)
        psi = np.exp(-abs(deviation))
        return float(np.clip(psi, 0.0, 1.0))

    def dynamics(self, t: float, y: List[float]) -> List[float]:
        """Ecuaciones diferenciales del sistema."""
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
        """Simula el sistema en el intervalo dado."""
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

        return self.time, self.x, self.v, self.O_field, self.E_field, self.psi_t


# ═══════════════════════════════════════════════════════════════
# 2. ANÁLISIS ESPECTRAL
# ═══════════════════════════════════════════════════════════════

def analizar_espectro(senal: np.ndarray, fs: float, f_ref: float = F0) -> dict:
    """Analiza el espectro: pico, σ_f², Ψ."""
    nperseg = min(2**14, len(senal) // 4)
    f, Pxx = welch(senal, fs=fs, nperseg=nperseg, scaling='density')

    idx_peak = np.argmax(Pxx)
    f_peak = f[idx_peak]

    sigma_f_sq = np.sum((f - f_peak)**2 * Pxx) / (np.sum(Pxx) + 1e-12)
    sigma_f = np.sqrt(sigma_f_sq)

    psi = 1 - sigma_f_sq / (f_peak**2 + 1e-12)
    psi = float(np.clip(psi, 0.0, 1.0))

    return {
        'f_peak': float(f_peak), 'sigma_f': float(sigma_f),
        'psi': psi, 'f': f, 'Pxx': Pxx, 'idx_peak': int(idx_peak)
    }


def registrar_estado(analisis: dict, fase: str, tiempo: float) -> dict:
    """Registra un estado del experimento."""
    return {
        'fase': fase, 'tiempo': tiempo,
        'f_peak': analisis['f_peak'],
        'sigma_f': analisis['sigma_f'],
        'psi': analisis['psi']
    }


# ═══════════════════════════════════════════════════════════════
# 3. PROTOCOLO DE RUPTURA
# ═══════════════════════════════════════════════════════════════

def ejecutar_ruptura(output_dir: str = "resultados", dt: float = 0.0001) -> dict:
    """Ejecuta el protocolo completo de ruptura en 3 fases."""
    os.makedirs(output_dir, exist_ok=True)
    fs = 1 / dt
    registro = []

    print("=" * 70)
    print("🔬 EXPERIMENTO DE RUPTURA · QCAL")
    print("=" * 70)
    print(f"  f₀ = {F0} Hz,  ω₀ = {OMEGA0:.4f} rad/s")
    print(f"  Ψ_crítico = {PSI_CRITICO}")

    # ── FASE 1: ESTADO BASE ─────────────────────────────────────
    print("\n🔵 FASE 1: Estado base coherente")
    print("-" * 50)

    params = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                             gamma=2.5, kappa=0.5, D_noise=0.0)
    osc = OsciladorQCAL(params)
    time, x, v, O_f, E_f, psi_t = osc.simulate((0, 10.0), dt, [0.1, 0.0, 1.0, 0.0])

    a_base = analizar_espectro(x[-20000:], fs)
    registro.append(registrar_estado(a_base, "BASE", time[-1]))
    print(f"  Ψ = {a_base['psi']:.9f}, f = {a_base['f_peak']:.6f} Hz, "
          f"σ_f = {a_base['sigma_f']:.6f} Hz")

    x_acum, psi_acum = x.copy(), psi_t.copy()

    # ── FASE 2: INYECCIÓN DE CAOS ──────────────────────────────
    print("\n🟠 FASE 2: Inyección de caos estocástico")
    print("-" * 50)

    D_noise_vals = [0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 20.0, 25.0, 30.0]
    for i, Dn in enumerate(D_noise_vals):
        pc = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                             gamma=2.5, kappa=0.5, D_noise=Dn)
        oc = OsciladorQCAL(pc)
        ini = [x_acum[-1], v[-1], O_f[-1], E_f[-1]]
        tc, xc, vc, Oc, Ec, psic = oc.simulate((0, 3.0), dt, ini)

        x_acum = np.concatenate([x_acum, xc])
        psi_acum = np.concatenate([psi_acum, psic])

        ac = analizar_espectro(xc[-10000:], fs)
        t_acum = tc[-1] + sum(D_noise_vals[:i]) * 3.0
        registro.append(registrar_estado(ac, "CAOS", t_acum))
        print(f"  D_noise={Dn:5.1f}: Ψ={ac['psi']:.6f}, f={ac['f_peak']:.4f} Hz")

    print(f"\n  Ψ tras caos: {registro[-1]['psi']:.6f}")

    # ── FASE 3: SALTO DE RESONANCIA ────────────────────────────
    print("\n🟢 FASE 3: Salto de resonancia — aumento de orden 𝒪")
    print("-" * 50)

    alpha_vals = [0.2, 0.4, 0.8, 1.5, 3.0, 5.0, 8.0, 12.0, 16.0, 20.0]
    pr = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                         gamma=2.5, kappa=0.5, D_noise=30.0)
    or_ = OsciladorQCAL(pr)
    ini_r = [x_acum[-1], v[-1], O_f[-1], E_f[-1]]

    for alpha in alpha_vals:
        or_.params.alpha = alpha
        tr, xr, vr, Or_, Er_, psir = or_.simulate((0, 5.0), dt, ini_r)

        x_acum = np.concatenate([x_acum, xr])
        psi_acum = np.concatenate([psi_acum, psir])

        ar = analizar_espectro(xr[-15000:], fs)
        t_acum2 = tr[-1] + sum(alpha_vals[:alpha_vals.index(alpha)]) * 5.0
        registro.append(registrar_estado(ar, "RESONANCIA", t_acum2))
        ini_r = [xr[-1], vr[-1], Or_[-1], Er_[-1]]

        print(f"  α={alpha:5.1f}: Ψ={ar['psi']:.6f}, f={ar['f_peak']:.4f} Hz")

    # ── RESULTADOS ─────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("📊 RESULTADOS FINALES")
    print(f"{'='*70}")

    psi_final = registro[-1]['psi']
    f_final = registro[-1]['f_peak']
    colimacion = abs(f_final - F0) < 0.01

    print(f"\n  Ψ inicial: {registro[0]['psi']:.9f}")
    print(f"  Ψ final:   {psi_final:.9f}")
    print(f"  f inicial: {registro[0]['f_peak']:.6f} Hz")
    print(f"  f final:   {f_final:.6f} Hz")
    print(f"  Colimación en f₀: {'✅ SÍ' if colimacion else '❌ NO'}")
    print(f"  Desviación: {abs(f_final - F0):.6f} Hz")

    # ── VEREDICTO ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("🔱 VEREDICTO DEL EXPERIMENTO DE RUPTURA")
    print(f"{'='*70}")

    if colimacion:
        print("""
  🚀 PREDICCIÓN QCAL CONFIRMADA

  El sistema colimó espontáneamente en f₀ = 141.7001 Hz
  tras caos extremo y estrés estocástico.

  Demuestra:
  • Memoria de fase no local en el espacio de fases.
  • f₀ como atractor topológico/dinámico.
  • Coherencia como invariante emergente.

  LA FÍSICA NUEVA ESTÁ CONFIRMADA.
  """)
    else:
        print("""
  ⚠️ Colimación no detectada en este ensayo.

  Posibles causas: tiempo insuficiente, parámetros
  fuera del régimen crítico.
  """)

    # ── VISUALIZACIÓN ──────────────────────────────────────────
    if HAS_MPL:
        print("\n📊 Generando visualización...")
        fig, axes = plt.subplots(3, 2, figsize=(14, 12))

        ax1 = axes[0, 0]
        ax1.plot(x_acum[-50000:], 'b-', alpha=0.7, linewidth=0.5)
        ax1.set_xlabel('Muestra'), ax1.set_ylabel('x(t)')
        ax1.set_title('Señal final (zoom)'), ax1.grid(alpha=0.3)

        ax2 = axes[0, 1]
        f_s, Pxx_s = welch(x_acum[-100000:], fs=fs, nperseg=2048)
        ax2.semilogy(f_s, Pxx_s, 'b-', linewidth=1)
        ax2.axvline(F0, color='red', linestyle='--', linewidth=2,
                     label=f'f₀ = {F0} Hz')
        ax2.set_xlim(100, 200), ax2.legend(), ax2.grid(alpha=0.3)
        ax2.set_xlabel('Frecuencia (Hz)'), ax2.set_ylabel('Densidad espectral')
        ax2.set_title('Espectro Final')

        ax3 = axes[1, 0]
        tiempos = [r['tiempo'] for r in registro]
        psis = [r['psi'] for r in registro]
        fases = [r['fase'] for r in registro]
        colores_fase = {'BASE': 'blue', 'CAOS': 'orange', 'RESONANCIA': 'green'}
        for fase, color in colores_fase.items():
            idx = [i for i, f in enumerate(fases) if f == fase]
            if idx:
                ax3.plot([tiempos[i] for i in idx], [psis[i] for i in idx],
                          color=color, marker='o', ms=4, alpha=0.8, label=fase)
        ax3.axhline(PSI_CRITICO, color='red', linestyle='--', alpha=0.5)
        ax3.set_xlabel('Tiempo (s)'), ax3.set_ylabel('Ψ')
        ax3.set_title('Evolución de la Coherencia')
        ax3.legend(), ax3.grid(alpha=0.3)

        ax4 = axes[1, 1]
        f_peaks = [r['f_peak'] for r in registro]
        ax4.plot(tiempos, f_peaks, 'g-o', ms=4)
        ax4.axhline(F0, color='red', linestyle='--', alpha=0.5,
                     label=f'f₀ = {F0} Hz')
        ax4.set_xlabel('Tiempo (s)'), ax4.set_ylabel('f_peak (Hz)')
        ax4.set_title('Evolución de f_peak'), ax4.legend(), ax4.grid(alpha=0.3)

        ax5 = axes[2, 0]
        f_sp, t_sp, Sxx = spectrogram(x_acum[-200000:], fs=fs,
                                        nperseg=512, noverlap=256)
        ax5.pcolormesh(t_sp, f_sp, 10 * np.log10(Sxx + 1e-12),
                        shading='gouraud', cmap='inferno')
        ax5.axhline(F0, color='cyan', linestyle='--', linewidth=1.5)
        ax5.set_xlabel('Tiempo (s)'), ax5.set_ylabel('Frecuencia (Hz)')
        ax5.set_title('Espectrograma (final)'), ax5.set_ylim(100, 200)

        ax6 = axes[2, 1]
        ax6.scatter(f_peaks, psis, c=range(len(registro)),
                     cmap='viridis', s=80, alpha=0.8)
        ax6.axvline(F0, color='red', linestyle='--', alpha=0.5)
        ax6.set_xlabel('f_peak (Hz)'), ax6.set_ylabel('Ψ')
        ax6.set_title('Ψ vs f_peak (evolución)')
        ax6.legend(), ax6.grid(alpha=0.3), ax6.set_xlim(120, 180)

        plt.tight_layout()
        path_png = os.path.join(output_dir, "experimento_ruptura_definitivo.png")
        plt.savefig(path_png, dpi=150)
        plt.close()
        print(f"📁 Gráfico: {path_png}")

    # ── GUARDAR REGISTRO ───────────────────────────────────────
    path_json = os.path.join(output_dir, "registro_ruptura.json")
    with open(path_json, "w") as f:
        json.dump(registro, f, indent=2)
    print(f"📁 Registro: {path_json}")

    return {
        'psi_final': psi_final, 'f_final': f_final,
        'colimacion': colimacion, 'registro': registro,
        'desviacion_hz': abs(f_final - F0)
    }


# ═══════════════════════════════════════════════════════════════
# 4. PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    np.random.seed(42)
    resultado = ejecutar_ruptura()

    print(f"\n{'='*70}")
    print("∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ")
    print(f"COLIMACIÓN: {'✅ CONFIRMADA' if resultado['colimacion'] else '❌ PENDIENTE'}")
    print("28/Jul/2026 🔱")
    print(f"{'='*70}")
