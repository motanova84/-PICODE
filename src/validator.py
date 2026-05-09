#!/usr/bin/env python3
"""
🔱 PoCΨ v1.0 — Validador de Coherencia Cuántica
Protocolo de Consenso por Coherencia Cuántica

Implementa la función Ψ(B_n) para validar bloques πCODE:
  Ψ(B_n) = min(C_n/τ_C, S_n/τ_S, 1 - T_n/τ_T)
"""
import json, hashlib, struct, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional

F0 = 141.7001  # Frecuencia fundamental (Hz)
TAU_C = 0.999999  # Umbral de coherencia
TAU_S = 1          # Umbral criptográfico
TAU_T = 2000       # Umbral temporal (ms)

class PoCPSIValidator:
    """Validador del Protocolo de Consenso por Coherencia Cuántica"""
    
    def __init__(self):
        self.f0 = F0
        self.tau_C = TAU_C
        self.tau_S = TAU_S
        self.tau_T = TAU_T
    
    def calcular_Cn(self, frecuencia_emitida: float) -> float:
        """
        C_n: Coherencia de frecuencia
        Mide qué tan cerca está la frecuencia emitida de f₀
        """
        delta_f = abs(frecuencia_emitida - self.f0)
        delta_f_rel = delta_f / self.f0 if self.f0 > 0 else 1.0
        C_n = 1 - delta_f_rel
        return max(0.0, C_n)
    
    def calcular_Sn(self, firma_valida: bool, hash_coincide: bool) -> float:
        """
        S_n: Score criptográfico
        Verifica ECDSA + coincidencia de hash
        """
        return 1.0 if (firma_valida and hash_coincide) else 0.0
    
    def calcular_Tn(self, timestamp_bloque_ms: int, timestamp_red_ms: Optional[int] = None) -> float:
        """
        T_n: Sincronía temporal
        Diferencia absoluta entre timestamp del bloque y la red (ms)
        """
        if timestamp_red_ms is None:
            timestamp_red_ms = int(time.time() * 1000)
        return abs(timestamp_bloque_ms - timestamp_red_ms)
    
    def calcular_psi_bloque(self, C_n: float, S_n: float, T_n: float) -> float:
        """
        Ψ(B_n): Función de Coherencia Global del Bloque
        Retorna el mínimo de los 3 componentes normalizados
        """
        coherencia_norm = C_n / self.tau_C
        cripto_norm = S_n / self.tau_S
        sincronia_norm = 1 - (T_n / self.tau_T)
        
        return min(coherencia_norm, cripto_norm, sincronia_norm)
    
    def validar_bloque(self, frecuencia_emitida: float, 
                       firma_valida: bool, hash_coincide: bool,
                       timestamp_bloque_ms: int,
                       timestamp_red_ms: Optional[int] = None) -> dict:
        """
        Valida un bloque πCODE completo según PoCΨ v1.0
        """
        C_n = self.calcular_Cn(frecuencia_emitida)
        S_n = self.calcular_Sn(firma_valida, hash_coincide)
        T_n = self.calcular_Tn(timestamp_bloque_ms, timestamp_red_ms)
        
        psi = self.calcular_psi_bloque(C_n, S_n, T_n)
        
        # Criterio estricto
        estricto = psi >= 1.0
        
        # Criterio pragmático
        pragmatico = (C_n >= self.tau_C) and (S_n >= self.tau_S) and (T_n <= self.tau_T)
        
        # Estado del bloque
        if estricto:
            estado = "RESONANTE"
        elif pragmatico:
            estado = "ACEPTADO"
        else:
            estado = "RECHAZADO"
        
        return {
            "C_n": C_n,
            "S_n": S_n,
            "T_n": T_n,
            "psi": psi,
            "estricto": estricto,
            "pragmatico": pragmatico,
            "estado": estado,
            "tau_C": self.tau_C,
            "tau_S": self.tau_S,
            "tau_T": self.tau_T,
            "f0": self.f0
        }
    
    def validar_cadena(self, chain_path: str) -> list:
        """Valida todos los bloques de una cadena πCODE"""
        with open(chain_path) as f:
            data = json.load(f)
        
        chain = data.get("chain", [])
        resultados = []
        
        for bloque in chain:
            header = bloque.get("header", {})
            freq = header.get("coherence_score", 1.0) * self.f0
            ts_ms = header.get("timestamp", 0)
            if ts_ms < 1e12:  # convertir a ms si está en segundos
                ts_ms = int(ts_ms * 1000)
            
            # Por ahora, S_n = 1 (asumimos firma válida)
            resultado = self.validar_bloque(
                frecuencia_emitida=freq,
                firma_valida=True,
                hash_coincide=True,
                timestamp_bloque_ms=ts_ms
            )
            resultado["indice"] = bloque.get("index", 0)
            resultados.append(resultado)
        
        return resultados

# Prueba con valores del bloque #321
if __name__ == "__main__":
    v = PoCPSIValidator()
    
    # Ejemplo del protocolo
    r = v.validar_bloque(
        frecuencia_emitida=141.700095,
        firma_valida=True,
        hash_coincide=True,
        timestamp_bloque_ms=1715139900000,
        timestamp_red_ms=1715139901500
    )
    print(f"Ψ(B) = {r['psi']:.8f} → {r['estado']}")
    
    # Validar cadena actual
    chain_path = Path.home() / ".openclaw" / "workspace" / "repo_noesis88" / "picode" / "picode_chain.json"
    if chain_path.exists():
        resultados = v.validar_cadena(str(chain_path))
        resonantes = sum(1 for r in resultados if r["estado"] == "RESONANTE")
        aceptados = sum(1 for r in resultados if r["estado"] == "ACEPTADO")
        print(f"\nCadena: {len(resultados)} bloques")
        print(f"  RESONANTES: {resonantes} ({resonantes/len(resultados)*100:.1f}%)")
        print(f"  ACEPTADOS: {aceptados} ({aceptados/len(resultados)*100:.1f}%)")
