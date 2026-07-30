"""
Post & Catalog Use Cases — PipelineFace (Clean Architecture)
=============================================================
Casos de uso para gerenciamento, listagem e download em lote dos posts catalogados.
"""

from typing import Dict, Any, Callable, List, Optional
from web.domain.entities import ProfilePost
from web.domain.repositories import AbstractProfilePostRepository, AbstractAppConfigRepository


class ListProfilePostsUseCase:
    def __init__(self, repository: AbstractProfilePostRepository):
        self.repository = repository

    def execute(self, profile_url: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> List[ProfilePost]:
        return self.repository.list_posts(profile_url=profile_url, status=status, limit=limit)


class GetPostStatsUseCase:
    def __init__(self, repository: AbstractProfilePostRepository):
        self.repository = repository

    def execute(self, profile_url: Optional[str] = None) -> Dict[str, int]:
        return self.repository.get_stats(profile_url=profile_url)


class UpdatePostStatusUseCase:
    def __init__(self, repository: AbstractProfilePostRepository):
        self.repository = repository

    def execute(self, post_id: str, status: str, error_message: Optional[str] = None) -> bool:
        return self.repository.update_status(post_id=post_id, status=status, error_message=error_message)


class DeletePostUseCase:
    def __init__(self, repository: AbstractProfilePostRepository):
        self.repository = repository

    def execute(self, post_id: str) -> bool:
        return self.repository.delete_post(post_id=post_id)


class RunListPostsUseCase:
    def __init__(self, run_process_func: Callable[[List[str], str], None], config_repo: AbstractAppConfigRepository):
        self.run_process_func = run_process_func
        self.config_repo = config_repo

    def execute(self, target_url: str, max_scrolls: Optional[int] = None) -> Dict[str, str]:
        configs = self.config_repo.as_dict()
        resolved_max_scrolls = max_scrolls or int(configs.get("list_posts_max_scrolls", 100))

        cmd = ["python3", "scraper/facebook_scraper.py", "--target", target_url, "--list-posts", "--max-scrolls", str(resolved_max_scrolls)]
        self.run_process_func(cmd, f"Listagem de Posts ({target_url})")
        return {"status": "started", "message": f"Listagem de posts iniciada para {target_url}"}


class RunDownloadPendingUseCase:
    def __init__(self, run_process_func: Callable[[List[str], str], None], config_repo: AbstractAppConfigRepository):
        self.run_process_func = run_process_func
        self.config_repo = config_repo

    def execute(self, target_url: str, batch_size: Optional[int] = None) -> Dict[str, str]:
        configs = self.config_repo.as_dict()
        resolved_batch_size = batch_size or int(configs.get("scraper_download_batch_size", 10))

        cmd = ["python3", "scraper/facebook_scraper.py", "--target", target_url, "--download-pending", "--batch-size", str(resolved_batch_size)]
        self.run_process_func(cmd, f"Download em Lote ({resolved_batch_size} posts)")
        return {"status": "started", "message": f"Download de {resolved_batch_size} posts pendentes iniciado para {target_url}"}


class GetSinglePostUseCase:
    def __init__(self, repository: AbstractProfilePostRepository):
        self.repository = repository

    def execute(self, post_id: str) -> Optional[ProfilePost]:
        return self.repository.find_by_post_id(post_id)


class RunDownloadSinglePostUseCase:
    def __init__(self, run_process_func: Callable[[List[str], str], None], repository: AbstractProfilePostRepository):
        self.run_process_func = run_process_func
        self.repository = repository

    def execute(self, post_id: str) -> Dict[str, str]:
        post = self.repository.find_by_post_id(post_id)
        if not post:
            raise KeyError(f"Post {post_id} não encontrado")

        cmd = ["python3", "scraper/facebook_scraper.py", "--target", post.profile_url, "--download-pending", "--batch-size", "1"]
        self.run_process_func(cmd, f"Download do Post ({post_id})")
        return {"status": "started", "message": f"Download do post {post_id} iniciado"}

