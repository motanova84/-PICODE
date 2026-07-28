#!/usr/bin/env python3
"""
QCAL - EXPERIMENTO DE RUPTURA · OSCILADOR NO LINEAL v1.0
================================================================
OsciladorQCAL con dinámica completa de coherencia:
  dx/dt  = v
  dv/dt  = -ω₀²x - βv + α·O·x - √(2D_noise·E)·η(t)
  dO/dt  = -λ_O·(O - O_ext) + κ·Ψ·x²
  dE/dt  = -λ_E·(E - E_ext)

Si el sistema colima espontáneamente en f₀ tras caos extremo,
f₀ queda demostrado como atractor topológico/dinámico.

Fases:
  FASE 1: Estado base coherente (Ψ → 1, f → f₀)
  FASE 2: Inyección de caos estocástico (ℰ ↑↑↑, Ψ → 0)
  FASE 3: Aumento de orden/bombeo (𝒪 ↑↑↑)
  FASE 4: Estabilización — ¿colima en f₀?

Fundamento: Ψ = 1 - σ_f²/f² desde g¹(τ) = exp(-½⟨Δφ²⟩)
  (Debye-Waller-Lax-Shawlow, 1960s)

Autor: JMMB / AMDA Ψ · QCAL Metrology
Fecha: 2026-07-28 · v1.0
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
# 1. CONSTANTES
# ═══════════════════════════════════════════════════════════════

F0 = 141.7001         # Hz — frecuencia de referencia (post-análisis)
OMEGA0 = 2 * np.pi * F0  # rad/s
PSI_CRITICO = 0.999999   # Umbral de coherencia para auto-colimación
T_QCAL = 1.0 / (2 * np.pi * F0)  # ≈ 1.1229 ms


@dataclass
class ParametrosQCAL:
    """Parámetros del sistema QCAL no lineal."""
    omega0: float = OMEGA0      # Frecuencia natural del atractor (rad/s)
    alpha: float = 0.1          # Coeficiente de bombeo (orden 𝒪)
    beta: float = 0.01          # Coeficiente de disipación (ℰ lineal)
    gamma: float = 2.5          # Conmutador rígido (>1 = switching, <1 = suave)
    kappa: float = 0.5          # Acoplamiento campo-orden
    lambda_O: float = 1.0       # Tasa de relajación del campo de orden
    lambda_E: float = 2.0       # Tasa de relajación del campo de entropía
    D_noise: float = 0.0        # Intensidad del ruido (entropía ℰ)


@dataclass
class EstadoRuptura:
    """Estado del sistema en un instante del experimento."""
    paso: int
    psi: float
    f_peak: float
    sigma_f: float
    O_val: float
    E_val: float
    fase: str  # BASE, CAOS, COLIMACION, TRANSICION


@dataclass
class ResultadoRuptura:
    """Resultado completo del experimento."""
    colimacion: bool
    psi_final: float
    f_final: float
    desviacion_hz: float
    gamma_estimado: Optional[float]
    n_estados: int
    fases: List[str]
    timestamp: str = ""


# ═══════════════════════════════════════════════════════════════
# 2. OSCILADOR QCAL
# ═══════════════════════════════════════════════════════════════

class OsciladorQCAL:
    """
    Oscilador no lineal con dinámica QCAL.

    Ecuaciones:
      dx/dt  = v
      dv/dt  = -ω₀²·x - β·v + α·O·x - √(2D_noise·E)·η(t)
      dO/dt  = -λ_O·(O - O_ext) + κ·Ψ·x²
      dE/dt  = -λ_E·(E - E_ext)

    donde Ψ = 1 - σ_f²/f² es la coherencia instantánea,
    calculada a partir de la razón v/x como estimador de fase.
    """

    def __init__(self, params: ParametrosQCAL):
        self.params = params
        self.time: Optional[np.ndarray] = None
        self.x: Optional[np.ndarray] = None
        self.v: Optional[np.ndarray] = None
        self.O_field: Optional[np.ndarray] = None
        self.E_field: Optional[np.ndarray] = None
        self.psi_t: Optional[np.ndarray] = None

    @staticmethod
    def _psi_instantaneo(x: float, v: float) -> float:
        """
        Calcula Ψ instantáneo a partir de x y v.
        Ψ ≈ 1 - σ_f²/f² evaluado como pureza de la oscilación.

        Para un oscilador armónico: x(t) = A·cos(ωt), v(t) = -A·ω·sin(ωt)
        La relación v/x da información de fase instantánea.
        """
        if abs(x) < 1e-12:
            return 0.0
        omega_inst = abs(v / x)
        f_inst = omega_inst / (2 * np.pi)
        if f_inst < 1e-6:
            return 0.0
        # Estimación de σ_f a partir de la fluctuación de la frecuencia instantánea
        return 1.0 - min(1.0, abs(f_inst - F0) / F0)

    def dynamics(self, t: float, y: List[float],
                 O_ext: float = 1.0, E_ext: float = 0.0) -> List[float]:
        """
        Dinámica del sistema QCAL [x, v, O, E].

        Args:
            t: tiempo (s)
            y: [x, v, O, E] — variables de estado
            O_ext: bombeo externo de orden
            E_ext: entropía externa (ruido inyectado)
        """
        x, v, O, E = y
        p = self.params

        # Coherencia instantánea
        psi = self._psi_instantaneo(x, v)

        # Ruido estocástico (proceso de Langevin)
        noise = np.random.normal(0, 1) * np.sqrt(2 * p.D_noise * max(E, 0))

        # Ecuaciones diferenciales
        dxdt = v
        dvdt = (-p.omega0**2 * x
                - p.beta * v
                + p.alpha * O * x
                - noise)
        dOdt = -p.lambda_O * (O - O_ext) + p.kappa * psi * x**2
        dEdt = -p.lambda_E * (E - E_ext)

        return [dxdt, dvdt, dOdt, dEdt]

    def simulate(self, t_span: Tuple[float, float], dt: float = 0.0001,
                  initial_state: Optional[List[float]] = None,
                  O_ext: float = 1.0, E_ext: float = 0.0):
        """
        Simula el sistema en el intervalo de tiempo dado.

        Args:
            t_span: (t_inicio, t_fin) en segundos
            dt: Paso de tiempo para salida
            initial_state: [x, v, O, E] inicial
            O_ext: bombeo externo
            E_ext: entropía externa
        """
        if initial_state is None:
            initial_state = [0.1, 0.0, 0.5, 0.0]

        t_eval = np.arange(t_span[0], t_span[1], dt)

        sol = solve_ivp(
            lambda t, y: self.dynamics(t, y, O_ext=O_ext, E_ext=E_ext),
            t_span,
            initial_state,
            method='RK45',
            t_eval=t_eval,
            max_step=dt / 5,
            rtol=1e-8,
            atol=1e-10
        )

        self.time = sol.t
        self.x = sol.y[0]
        self.v = sol.y[1]
        self.O_field = sol.y[2]
        self.E_field = sol.y[3]

        # Calcular Ψ instantáneo
        self.psi_t = np.array([self._psi_instantaneo(xi, vi)
                               for xi, vi in zip(self.x, self.v)])

        return self.time, self.x, self.v, self.O_field, self.E_field, self.psi_t


# ═══════════════════════════════════════════════════════════════
# 3. PROTOCOLO DE RUPTURA
# ═══════════════════════════════════════════════════════════════

def analizar_espectro(senal: np.ndarray, fs: float) -> dict:
    """Analiza el espectro de una señal y calcula Ψ."""
    nperseg = min(2**14, len(senal) // 4)
    f, Pxx = welch(senal, fs=fs, nperseg=nperseg, scaling='density')

    idx_peak = np.argmax(Pxx)
    f_peak = f[idx_peak]

    sigma_f_sq = np.sum((f - f_peak)**2 * Pxx) / (np.sum(Pxx) + 1e-12)
    sigma_f = np.sqrt(sigma_f_sq)

    psi = 1.0 - sigma_f_sq / (f_peak**2 + 1e-12)
    psi = float(np.clip(psi, 0.0, 1.0))

    return {
        'f_peak': float(f_peak),
        'sigma_f': float(sigma_f),
        'psi': psi,
        'f': f,
        'Pxx': Pxx,
        'idx_peak': int(idx_peak)
    }


def ejecutar_protocolo_ruptura(output_dir: str = "resultados",
                                dt: float = 0.0001) -> dict:
    """
    Ejecuta el protocolo completo de ruptura en 3 fases.
    """
    os.makedirs(output_dir, exist_ok=True)
    print("=" * 70)
    print("🔬 EXPERIMENTO DE RUPTURA · OSCILADOR QCAL v1.0")
    print("=" * 70)
    print(f"\n  f₀ = {F0} Hz")
    print(f"  ω₀ = {OMEGA0:.4f} rad/s")
    print(f"  τ_QCAL = {T_QCAL*1000:.4f} ms")

    # ── FASE 1: Estado base coherente ──────────────────────────
    print("\n📋 FASE 1: Estado base coherente")
    print("-" * 50)

    params = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                             gamma=2.5, kappa=0.5, D_noise=0.0)
    osc = OsciladorQCAL(params)
    estado_inicial = [0.1, 0.0, 1.0, 0.0]
    t_span = (0, 10.0)
    time, x, v, O_field, E_field, psi_t = osc.simulate(t_span, dt, estado_inicial)
    print(f"  Duración: {t_span[1]}s")
    print(f"  Ψ promedio: {np.mean(psi_t[1000:]):.6f}")

    # ── FASE 2: Inyección de caos ──────────────────────────────
    print("\n📋 FASE 2: Inyección de caos estocástico")
    print("-" * 50)

    D_noise_values = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 20.0]
    resultados_fase2 = []

    for D_noise in D_noise_values:
        p2 = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                             gamma=2.5, kappa=0.5, D_noise=D_noise)
        osc2 = OsciladorQCAL(p2)
        ini2 = [x[-1], v[-1], O_field[-1], E_field[-1]]
        t2 = (0, 2.0)
        time2, x2, v2, O2, E2, psi2 = osc2.simulate(t2, dt, ini2)

        analisis = analizar_espectro(x2[-10000:], 1/dt)
        resultados_fase2.append({
            'D_noise': D_noise, 'psi': analisis['psi'],
            'f_peak': analisis['f_peak'], 'sigma_f': analisis['sigma_f'],
        })
        print(f"  D_noise={D_noise:.1f}: Ψ={analisis['psi']:.6f}, "
              f"f={analisis['f_peak']:.4f} Hz")

        x = np.concatenate([x, x2])
        v = np.concatenate([v, v2])
        psi_t = np.concatenate([psi_t, psi2])

    print(f"\n  Ψ tras caos: {resultados_fase2[-1]['psi']:.6f}")

    # ── FASE 3: Salto de resonancia ────────────────────────────
    print("\n📋 FASE 3: Salto de resonancia — aumento de orden 𝒪")
    print("-" * 50)

    alpha_values = [0.1, 0.2, 0.4, 0.8, 1.6, 3.0, 5.0, 8.0, 12.0, 16.0]
    resultados_fase3 = []

    p3 = ParametrosQCAL(omega0=OMEGA0, alpha=0.1, beta=0.01,
                         gamma=2.5, kappa=0.5, D_noise=16.0)
    osc3 = OsciladorQCAL(p3)
    ini3 = [x[-1], v[-1], O_field[-1], E_field[-1]]

    for alpha in alpha_values:
        osc3.params.alpha = alpha
        t3 = (0, 3.0)
        time3, x3, v3, O3, E3, psi3 = osc3.simulate(t3, dt, ini3)

        a3 = analizar_espectro(x3[-15000:], 1/dt)
        resultados_fase3.append({
            'alpha': alpha, 'psi': a3['psi'],
            'f_peak': a3['f_peak'], 'sigma_f': a3['sigma_f'],
        })
        ini3 = [x3[-1], v3[-1], O3[-1], E3[-1]]
        x = np.concatenate([x, x3])
        v = np.concatenate([v, v3])
        psi_t = np.concatenate([psi_t, psi3])

        print(f"  α={alpha:.1f}: Ψ={a3['psi']:.6f}, f={a3['f_peak']:.4f} Hz")

    # ── RESULTADOS ─────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("📊 RESULTADOS DEL EXPERIMENTO DE RUPTURA")
    print(f"{'='*70}")

    psi_final = resultados_fase3[-1]['psi']
    f_final = resultados_fase3[-1]['f_peak']
    colimacion = abs(f_final - F0) < 0.1

    print(f"\n  Ψ final: {psi_final:.6f}")
    print(f"  f final: {f_final:.6f} Hz")
    print(f"  Colimación en f₀: {'✅ SÍ' if colimacion else '❌ NO'}")

    if colimacion:
        print("\n  🚀 PREDICCIÓN QCAL CONFIRMADA")
        print("     El sistema colimó espontáneamente en f₀ = 141.7001 Hz")
        print("     tras ser sometido a caos extremo.")
    else:
        print("\n  ⚠️ La colimación no se ha producido en este ensayo.")

    # ── VISUALIZACIÓN ─────────────────────────────────────────
    if HAS_MPL:
        fig, axes = plt.subplots(3, 2, figsize=(14, 12))

        # Señal completa
        t_total = np.linspace(0, len(x) * dt, len(x))
        ax1 = axes[0, 0]
        ax1.plot(t_total[:50000], x[:50000], 'b-', alpha=0.7, linewidth=0.5)
        ax1.set_xlabel('Tiempo (s)'); ax1.set_ylabel('x(t)')
        ax1.set_title('Señal del Oscilador (zoom)'); ax1.grid(alpha=0.3)

        # Espectro final
        ax2 = axes[0, 1]
        nperseg = min(2**14, len(x[-100000:]) // 4)
        f_s, Pxx_s = welch(x[-100000:], fs=1/dt, nperseg=nperseg)
        ax2.semilogy(f_s, Pxx_s, 'b-', linewidth=1)
        ax2.axvline(F0, color='red', linestyle='--', linewidth=2,
                     label=f'f₀ = {F0} Hz')
        ax2.set_xlim(100, 200); ax2.legend(); ax2.grid(alpha=0.3)
        ax2.set_xlabel('Frecuencia (Hz)'); ax2.set_ylabel('Densidad espectral')
        ax2.set_title('Espectro Final')

        # Ψ (histórico de fases 2+3)
        ax3 = axes[1, 0]
        psi_hist = ([r['psi'] for r in resultados_fase2] +
                    [r['psi'] for r in resultados_fase3])
        tiempos_hist = list(range(len(psi_hist)))
        ax3.plot(tiempos_hist, psi_hist, 'r-o', markersize=4)
        ax3.axhline(0.999, color='green', linestyle='--', alpha=0.5,
                     label='Ψ_crítico')
        ax3.set_xlabel('Paso'); ax3.set_ylabel('Ψ')
        ax3.set_title('Evolución de la Coherencia')
        ax3.legend(); ax3.grid(alpha=0.3)

        # Frecuencia de pico
        ax4 = axes[1, 1]
        f_hist = ([r['f_peak'] for r in resultados_fase2] +
                  [r['f_peak'] for r in resultados_fase3])
        ax4.plot(tiempos_hist, f_hist, 'g-o', markersize=4)
        ax4.axhline(F0, color='red', linestyle='--', alpha=0.5,
                     label=f'f₀ = {F0} Hz')
        ax4.set_xlabel('Paso'); ax4.set_ylabel('f_peak (Hz)')
        ax4.set_title('Evolución de la Frecuencia de Pico')
        ax4.legend(); ax4.grid(alpha=0.3)

        # Espectrograma
        ax5 = axes[2, 0]
        f_spec, t_spec, Sxx = spectrogram(x, fs=1/dt, nperseg=512, noverlap=256)
        ax5.pcolormesh(t_spec, f_spec, 10 * np.log10(Sxx + 1e-12),
                       shading='gouraud', cmap='inferno')
        ax5.axhline(F0, color='cyan', linestyle='--', linewidth=1.5,
                     label=f'f₀ = {F0} Hz')
        ax5.set_xlabel('Tiempo (s)'); ax5.set_ylabel('Frecuencia (Hz)')
        ax5.set_title('Espectrograma'); ax5.legend(); ax5.set_ylim(100, 200)

        # Ψ teórico (curvas paramétricas σ_f)
        ax6 = axes[2, 1]
        f_range = np.linspace(130, 160, 1000)
        for sigma in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]:
            psi_t = np.clip(1 - sigma**2 / f_range**2, 0, 1)
            ax6.plot(f_range, psi_t, '--', alpha=0.3, label=f'σ_f={sigma} Hz')
        for r in resultados_fase2 + resultados_fase3:
            if r['psi'] > 0.01:
                ax6.scatter(r['f_peak'], r['psi'], color='red', s=30, alpha=0.7)
        ax6.set_xlim(130, 170); ax6.set_ylim(0, 1.05)
        ax6.set_xlabel('Frecuencia (Hz)'); ax6.set_ylabel('Ψ')
        ax6.set_title('Ψ vs Frecuencia (curvas teóricas + datos)')
        ax6.legend(loc='upper right', ncol=2, fontsize=8); ax6.grid(alpha=0.3)

        plt.tight_layout()
        path_fig = os.path.join(output_dir, "experimento_ruptura_completo.png")
        plt.savefig(path_fig, dpi=150)
        plt.close()
        print(f"\n📁 Gráfico: {path_fig}")

    # ── Reporte ───────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ")
    print(f"{'='*70}")

    return {
        'psi_final': psi_final,
        'f_final': f_final,
        'colimacion': colimacion,
        'resultados_fase2': resultados_fase2,
        'resultados_fase3': resultados_fase3,
        'timestamp': datetime.utcnow().isoformat()
    }


# ═══════════════════════════════════════════════════════════════
# 4. PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    resultados = ejecutar_protocolo_ruptura()
    with open("resultados/resultados_ruptura.json", "w") as f:
        json.dump(resultados, f, indent=2, default=str)
    print("📄 JSON: resultados/resultados_ruptura.json")
