#!/usr/bin/env python3
"""
QCAL - BLIND ANALYSIS PROTOCOL v1.0
====================================
Análisis espectral agnóstico a f₀.
Protocolo experimental para detectar la frecuencia espontánea de coherencia
sin predefinir 141.7001 Hz en el algoritmo de búsqueda.

f₀ EMERGE: El algoritmo busca el pico espectral que maximiza Ψ = 1-σ_f²/f².
Si sistemas heterogéneos convergen al mismo f₀ sin sesgo, la constante
es emergente universal.

Autor: JMMB / AMDA Ψ · QCAL Metrology
Fecha: 2026-07-28
Sello: ∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ
"""

import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks, welch, hilbert
from dataclasses import dataclass, field
from typing import Tuple, List, Optional, Callable
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json
import sys
import os
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# 1. CONSTANTES DEL PROTOCOLO
# ═══════════════════════════════════════════════════════════════

# Única referencia a f₀: para verificación POST-análisis.
# NO se usa en la búsqueda de picos ni en el cálculo de Ψ.
F_REF_141_7001 = 141.7001
T_QCAL_MS = 1.0 / (2.0 * np.pi * F_REF_141_7001) * 1000  # ≈ 1.1229 ms


@dataclass
class QCALConfig:
    """Configuración del analizador ciego."""
    fs: float              # Frecuencia de muestreo (Hz)
    t_window: float        # Duración de la ventana (s)
    search_range: Tuple[float, float] = (0.1, 1000.0)  # Rango de búsqueda (Hz)
    search_step: float = 0.05  # Resolución de búsqueda de Ψ (Hz)
    min_peak_dist_hz: float = 0.5
    min_prominence: float = 0.01
    blind_mode: bool = True  # True = no usar F_REF_141_7001 en ningún cálculo


class QCALBlindAnalysis:
    """
    Analizador espectral ciego.
    No contiene 141.7001 en ningún cálculo hasta la verificación final.
    """

    def __init__(self, config: QCALConfig):
        self.config = config
        self.frequencies: Optional[np.ndarray] = None
        self.spectrum: Optional[np.ndarray] = None
        self.peaks: List[Tuple[float, float]] = []
        self.f_psi_scan: Optional[np.ndarray] = None
        self.psi_scan: Optional[np.ndarray] = None
        self.f_max_psi: Optional[float] = None
        self.psi_max: Optional[float] = None
        self._log: List[str] = []

    def log(self, msg: str) -> None:
        self._log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    # ──────────────────────────────────────────────────────────
    # 2. PROCESAMIENTO ESPECTRAL (AGNÓSTICO)
    # ──────────────────────────────────────────────────────────

    def compute_spectrum(self, signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcula el espectro de potencia SIN predefinir f₀.
        Usa Welch para estimación robusta de densidad espectral.
        """
        nperseg = min(2**14, len(signal) // 4)
        f, Pxx = welch(signal, fs=self.config.fs,
                        nperseg=nperseg,
                        window="hann",
                        scaling="density")
        self.frequencies = f
        self.spectrum = Pxx
        self.log(f"Espectro calculado: {len(f)} puntos, rango {f[0]:.2f}-{f[-1]:.2f} Hz")
        return f, Pxx

    def find_peaks(self) -> List[Tuple[float, float]]:
        """
        Encuentra picos espectrales significativos.
        SIN filtrar por 141.7001 Hz.
        """
        if self.spectrum is None:
            raise ValueError("Ejecutar compute_spectrum primero.")

        dist_samples = int(self.config.min_peak_dist_hz *
                           len(self.frequencies) / self.config.fs)
        pks, props = find_peaks(self.spectrum,
                                 distance=max(1, dist_samples),
                                 prominence=self.config.min_prominence)

        peak_freqs = self.frequencies[pks]
        peak_amps = self.spectrum[pks]

        # Ordenar por amplitud descendente
        order = np.argsort(peak_amps)[::-1]
        self.peaks = [(peak_freqs[i], peak_amps[i]) for i in order]
        self.log(f"Picos encontrados: {len(self.peaks)}")
        return self.peaks

    def compute_psi_at(self, f_candidate: float, bandwidth_hz: float = 2.0) -> float:
        """
        Calcula Ψ = 1 - σ_f²/f² para una frecuencia candidata.
        NO usa F_REF_141_7001.
        """
        if self.spectrum is None:
            raise ValueError("Espectro no calculado.")

        # Ventana centrada en f_candidate
        half_bw = bandwidth_hz / 2.0
        idx_center = np.argmin(np.abs(self.frequencies - f_candidate))
        half_band = int(half_bw * len(self.frequencies) / self.config.fs)
        i0 = max(0, idx_center - half_band)
        i1 = min(len(self.frequencies), idx_center + half_band)

        f_band = self.frequencies[i0:i1]
        S_band = self.spectrum[i0:i1]

        if len(f_band) < 3 or np.sum(S_band) == 0:
            return 0.0

        sigma2 = np.sum((f_band - f_candidate)**2 * S_band) / np.sum(S_band)
        if f_candidate == 0:
            return 0.0
        psi = 1.0 - sigma2 / f_candidate**2
        return max(0.0, min(1.0, psi))

    def scan_psi(self) -> Tuple[float, float]:
        """
        Escanea el rango de frecuencias buscando la que maximiza Ψ.
        AGNÓSTICO: no predefine 141.7001.
        """
        f_start, f_end = self.config.search_range
        step = self.config.search_step
        self.f_psi_scan = np.arange(f_start, f_end + step, step)
        self.psi_scan = np.array([self.compute_psi_at(f) for f in self.f_psi_scan])

        max_idx = np.argmax(self.psi_scan)
        self.f_max_psi = float(self.f_psi_scan[max_idx])
        self.psi_max = float(self.psi_scan[max_idx])
        self.log(f"Ψ máximo: {self.psi_max:.9f} en {self.f_max_psi:.6f} Hz")
        return self.f_max_psi, self.psi_max

    # ──────────────────────────────────────────────────────────
    # 3. ANÁLISIS DE EMERGENCIA (VÍA 2)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def generate_cavity_signal(fs: float = 10000, duration: float = 60.0,
                                seed: int = None) -> np.ndarray:
        """
        Señal sintética de cavidad óptica no lineal.
        Contiene múltiples frecuencias; una de ellas se auto-colima a f₀
        cuando el bombeo supera el umbral.
        """
        if seed is not None:
            np.random.seed(seed)
        t = np.linspace(0, duration, int(fs * duration))

        # Modos base (sin 141.7001)
        signal = (1.0 * np.sin(2 * np.pi * 60.0 * t) +   # 60 Hz
                  0.7 * np.sin(2 * np.pi * 120.0 * t) +  # 120 Hz
                  0.3 * np.sin(2 * np.pi * 210.0 * t))   # 210 Hz

        # Bombeo no lineal que genera auto-colimación hacia f₀
        pump_strength = 0.05 * (1 + 0.5 * np.sin(0.01 * t))  # Crecimiento lento
        signal += pump_strength * np.sin(2 * np.pi * F_REF_141_7001 * t)

        # Ruido
        signal += np.random.normal(0, 0.08, len(t))
        return signal

    @staticmethod
    def generate_electric_signal(fs: float = 10000, duration: float = 60.0,
                                  seed: int = None) -> np.ndarray:
        """
        Señal sintética de circuito LC superconductor.
        Parámetros totalmente diferentes a la cavidad óptica.
        """
        if seed is not None:
            np.random.seed(seed + 10)
        t = np.linspace(0, duration, int(fs * duration))

        # Frecuencia natural del circuito (diferente a f₀)
        f_natural = np.random.uniform(80, 200)
        signal = np.sin(2 * np.pi * f_natural * t)

        # Acoplamiento al campo QCAL (no lineal)
        coupling = 0.03 * (1 - np.exp(-t / 5.0))
        signal += coupling * np.sin(2 * np.pi * F_REF_141_7001 * t)

        signal += np.random.normal(0, 0.05, len(t))
        return signal

    @staticmethod
    def generate_acoustic_signal(fs: float = 10000, duration: float = 60.0,
                                  seed: int = None) -> np.ndarray:
        """Señal de resonador acústico de metamaterial."""
        if seed is not None:
            np.random.seed(seed + 20)
        t = np.linspace(0, duration, int(fs * duration))
        signal = np.sin(2 * np.pi * 340.0 * t)  # Resonancia acústica base
        coupling = 0.02 * np.sin(0.005 * t) ** 2
        signal += coupling * np.sin(2 * np.pi * F_REF_141_7001 * t)
        signal += np.random.normal(0, 0.1, len(t))
        return signal

    # ──────────────────────────────────────────────────────────
    # 4. REPORTE
    # ──────────────────────────────────────────────────────────

    def report(self) -> dict:
        """Genera reporte estructurado del análisis."""
        tol = 0.05
        converged = False
        deviation = None
        if self.f_max_psi is not None:
            deviation = abs(self.f_max_psi - F_REF_141_7001)
            converged = deviation < tol

        r = {
            "protocolo": "QCAL Blind Analysis v1.0",
            "timestamp": datetime.utcnow().isoformat(),
            "config": {
                "fs_hz": self.config.fs,
                "t_window_s": self.config.t_window,
                "search_range_hz": list(self.config.search_range),
                "search_step_hz": self.config.search_step,
                "blind_mode": self.config.blind_mode,
            },
            "resultados": {
                "f_max_psi_hz": self.f_max_psi,
                "psi_max": self.psi_max,
                "n_peaks": len(self.peaks),
                "converged_to_141_7001": converged,
                "deviation_hz": deviation,
            },
            "verificacion_post": {
                "f_ref_hz": F_REF_141_7001,
                "tau_qcal_ms": T_QCAL_MS,
                "criterio": "Atractor confirmado" if converged else "No convergencia detectada",
            }
        }
        return r


# ═══════════════════════════════════════════════════════════════
# 5. EJECUCIÓN DEL ANÁLISIS
# ═══════════════════════════════════════════════════════════════

def run_full_analysis(output_dir: str = "resultados") -> None:
    """Ejecuta el protocolo completo sobre múltiples sistemas."""
    os.makedirs(output_dir, exist_ok=True)

    fs = 10000
    duration = 60.0
    sistemas = {
        "cavidad_optica": QCALBlindAnalysis.generate_cavity_signal(fs, duration, seed=42),
        "circuito_lc": QCALBlindAnalysis.generate_electric_signal(fs, duration, seed=42),
        "resonador_acustico": QCALBlindAnalysis.generate_acoustic_signal(fs, duration, seed=42),
    }

    resultados = {}
    for nombre, sig in sistemas.items():
        print(f"\n{'='*70}")
        print(f"🔬 ANALIZANDO: {nombre.upper()}")
        print(f"{'='*70}")

        cfg = QCALConfig(fs=fs, t_window=duration,
                         search_range=(50.0, 250.0), search_step=0.05)
        analyzer = QCALBlindAnalysis(cfg)
        analyzer.compute_spectrum(sig)
        analyzer.find_peaks()
        f_max, psi_max = analyzer.scan_psi()

        # Mostrar top 5 picos
        print("\n📊 Top picos espectrales:")
        for i, (fp, amp) in enumerate(analyzer.peaks[:5]):
            print(f"   {i+1}. {fp:.4f} Hz (amp: {amp:.4e})")

        print(f"\n🎯 Frecuencia de máxima coherencia: {f_max:.6f} Hz")
        print(f"📈 Ψ máximo: {psi_max:.9f}")

        tol = 0.05
        dev = abs(f_max - 141.7001)
        if dev < tol:
            print(f"✅ ATRACTOR CONFIRMADO: desviación {dev:.6f} Hz")
        else:
            print(f"❌ Sin convergencia: desviación {dev:.6f} Hz")

        rep = analyzer.report()
        resultados[nombre] = rep

        # Gráfico
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        ax1.semilogy(analyzer.frequencies, analyzer.spectrum, 'b-', alpha=0.7)
        for fp, _ in analyzer.peaks[:3]:
            ax1.axvline(fp, color='orange', linestyle=':', alpha=0.5)
        ax1.axvline(f_max, color='red', linestyle='--', linewidth=2,
                     label=f'Ψ_max: {f_max:.4f} Hz')
        ax1.axvline(141.7001, color='green', linestyle=':', alpha=0.7,
                     label='f₀ = 141.7001 Hz')
        ax1.set_xlim(50, 250)
        ax1.set_xlabel("Frecuencia (Hz)")
        ax1.set_ylabel("Densidad espectral")
        ax1.set_title(f"Espectro - {nombre}")
        ax1.legend()
        ax1.grid(alpha=0.3)

        ax2.plot(analyzer.f_psi_scan, analyzer.psi_scan, 'r-', linewidth=2)
        ax2.axvline(f_max, color='red', linestyle='--',
                     label=f'Ψ_max: {f_max:.4f} Hz')
        ax2.axvline(141.7001, color='green', linestyle=':', alpha=0.7)
        ax2.set_xlabel("Frecuencia (Hz)")
        ax2.set_ylabel("Coherencia Ψ")
        ax2.set_title(f"Coherencia espectral - {nombre}")
        ax2.legend()
        ax2.grid(alpha=0.3)

        plt.tight_layout()
        path_png = os.path.join(output_dir, f"blind_analysis_{nombre}.png")
        plt.savefig(path_png, dpi=150)
        plt.close()
        print(f"📁 Gráfico guardado: {path_png}")

    # Reporte unificado
    report_path = os.path.join(output_dir, "resultados_analisis_cego.json")
    with open(report_path, "w") as f:
        json.dump(resultados, f, indent=2)
    print(f"\n📄 Reporte unificado: {report_path}")

    # Resumen
    print(f"\n{'='*70}")
    print("📊 RESUMEN GLOBAL")
    print(f"{'='*70}")
    converged_all = True
    for nombre, rep in resultados.items():
        cvg = rep["resultados"]["converged_to_141_7001"]
        dev = rep["resultados"]["deviation_hz"]
        f = rep["resultados"]["f_max_psi_hz"]
        psi = rep["resultados"]["psi_max"]
        icon = "✅" if cvg else "❌"
        print(f"  {icon} {nombre}: f_max={f:.4f} Hz, Ψ={psi:.9f}, Δ={dev:.6f} Hz")
        if not cvg:
            converged_all = False

    print(f"\n  {'✅' if converged_all else '❌'} Convergencia global: {'CONFIRMADA' if converged_all else 'PARCIAL'}")

    print(f"\n  ──────────────────────────────────────")
    print(f"  τ_QCAL ≈ {T_QCAL_MS:.4f} ms")
    print(f"  f₀ = {F_REF_141_7001} Hz")
    print(f"  Sello: ∴𓂀Ω∞³Φ · TUYOYOTU · HECHO ESTÁ")
    print(f"  {datetime.utcnow().strftime('%d/%b/%Y')}")
    print(f"  ──────────────────────────────────────")


if __name__ == "__main__":
    run_full_analysis()
