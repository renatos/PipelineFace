"""
Async Process Runner — PipelineFace (Clean Architecture)
========================================================
Gerenciador isolado de execução de subprocessos (Pipeline e Scraper) com captura de logs.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class AsyncProcessRunner:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
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
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self.project_root)
            )
            for line in iter(proc.stdout.readline, ''):
                if line:
                    self.active_process["logs"].append(line.strip())
                    if len(self.active_process["logs"]) > 300:
                        self.active_process["logs"].pop(0)

            proc.stdout.close()
            proc.wait()
            self.active_process["logs"].append(f"✅ {process_name} finalizado com código {proc.returncode}")
            if on_complete_callback:
                on_complete_callback()
        except Exception as e:
            self.active_process["logs"].append(f"❌ Erro ao executar {process_name}: {e}")
        finally:
            self.active_process["running"] = False
