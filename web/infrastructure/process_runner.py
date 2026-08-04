"""
Async Process Runner — PipelineFace (Clean Architecture)
========================================================
Gerenciador isolado de execução de subprocessos (Pipeline e Scraper) com capacidade de encerramento (Kill/Terminate).
"""

import os
import subprocess
import signal
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class AsyncProcessRunner:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.proc: Optional[subprocess.Popen] = None
        self.active_process: Dict[str, Any] = {
            "name": None,
            "running": False,
            "started_at": None,
            "logs": []
        }

    def is_running(self) -> bool:
        return self.active_process["running"]

    def get_status(self) -> Dict[str, Any]:
        return self.active_process

    def run_process_async(self, command: List[str], process_name: str, on_complete_callback=None):
        self.active_process["name"] = process_name
        self.active_process["running"] = True
        self.active_process["started_at"] = datetime.now().isoformat()
        self.active_process["logs"] = [f"🚀 Iniciando {process_name}: {' '.join(command)}"]

        try:
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            self.proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self.project_root),
                env=env
            )
            for line in iter(self.proc.stdout.readline, ''):
                if line:
                    self.active_process["logs"].append(line.strip())
                    if len(self.active_process["logs"]) > 300:
                        self.active_process["logs"].pop(0)

            self.proc.stdout.close()
            self.proc.wait()
            self.active_process["logs"].append(f"✅ {process_name} finalizado com código {self.proc.returncode}")
            if on_complete_callback and self.proc.returncode == 0:
                on_complete_callback()
        except Exception as e:
            self.active_process["logs"].append(f"❌ Erro ao executar {process_name}: {e}")
        finally:
            self.active_process["running"] = False
            self.proc = None

    def terminate_process(self) -> Dict[str, str]:
        """Interrompe/cancela imediatamente o subprocesso em andamento."""
        if not self.active_process["running"] or not self.proc:
            return {"status": "not_running", "message": "Nenhum processo em execução no momento."}

        proc_name = self.active_process["name"]
        try:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

            self.active_process["logs"].append(f"🛑 {proc_name} foi interrompido pelo usuário.")
            self.active_process["running"] = False
            self.proc = None
            return {"status": "terminated", "message": f"Processo {proc_name} interrompido com sucesso."}
        except Exception as e:
            return {"status": "error", "message": f"Erro ao interromper processo: {e}"}
