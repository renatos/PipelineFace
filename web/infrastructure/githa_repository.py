"""
Githa Context Repository — PipelineFace (Clean Architecture)
============================================================
Conexão e consultas read-only ao banco PostgreSQL do projeto Githa
para extração do perfil e dados reais do Studio Githa.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False

from web.domain.entities import GithaContext, GithaService, GithaProfessional
from web.infrastructure.githa_config import get_githa_db_config


class GithaContextRepository:
    """Repositório de acesso somente-leitura ao banco de dados do Githa."""

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or get_githa_db_config()

    def _get_connection(self):
        """Retorna uma nova conexão com o PostgreSQL do Githa."""
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("Módulo 'psycopg2' não está instalado neste ambiente.")
        return psycopg2.connect(**self.db_config)

    def get_services(self) -> List[GithaService]:
        """Lista todos os serviços cadastrados no catálogo do Githa."""
        query = """
            SELECT id, name, price, duration_minutes, description, service_group, active
            FROM services
            ORDER BY active DESC, name ASC
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
                    return [
                        GithaService(
                            id=row["id"],
                            name=row["name"].strip() if row["name"] else "",
                            price=float(row["price"]) if row["price"] is not None else None,
                            duration_minutes=row["duration_minutes"],
                            description=row["description"],
                            service_group=row["service_group"],
                            active=bool(row["active"])
                        )
                        for row in rows
                    ]
        except Exception as e:
            print(f"[GithaContextRepository] Erro ao buscar serviços: {e}")
            return []

    def get_popular_services(self, limit: int = 15) -> List[GithaService]:
        """Lista os serviços mais demandados com contagem de agendamentos e faturamento."""
        query = """
            SELECT s.id, s.name, s.price, s.duration_minutes, s.description, s.service_group, s.active,
                   COUNT(a.id) AS appointment_count,
                   COALESCE(SUM(a.price), 0) AS total_revenue
            FROM services s
            LEFT JOIN appointments a ON a.service_id = s.id
            GROUP BY s.id, s.name, s.price, s.duration_minutes, s.description, s.service_group, s.active
            ORDER BY appointment_count DESC, total_revenue DESC
            LIMIT %s
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
                    return [
                        GithaService(
                            id=row["id"],
                            name=row["name"].strip() if row["name"] else "",
                            price=float(row["price"]) if row["price"] is not None else None,
                            duration_minutes=row["duration_minutes"],
                            description=row["description"],
                            service_group=row["service_group"],
                            active=bool(row["active"]),
                            appointment_count=int(row["appointment_count"]),
                            total_revenue=float(row["total_revenue"])
                        )
                        for row in rows
                    ]
        except Exception as e:
            print(f"[GithaContextRepository] Erro ao buscar serviços populares: {e}")
            return []

    def get_professionals(self) -> List[GithaProfessional]:
        """Lista a equipe de profissionais cadastradas."""
        query = """
            SELECT id, name, phone, active
            FROM professionals
            ORDER BY active DESC, name ASC
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
                    return [
                        GithaProfessional(
                            id=row["id"],
                            name=row["name"].strip() if row["name"] else "",
                            phone=row["phone"],
                            active=bool(row["active"])
                        )
                        for row in rows
                    ]
        except Exception as e:
            print(f"[GithaContextRepository] Erro ao buscar profissionais: {e}")
            return []

    def get_counts(self) -> Dict[str, int]:
        """Retorna contadores de clientes e agendamentos totais."""
        counts = {"clients": 0, "appointments": 0, "services": 0}
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM clients")
                    counts["clients"] = cur.fetchone()[0]

                    cur.execute("SELECT COUNT(*) FROM appointments")
                    counts["appointments"] = cur.fetchone()[0]

                    cur.execute("SELECT COUNT(*) FROM services")
                    counts["services"] = cur.fetchone()[0]
        except Exception as e:
            print(f"[GithaContextRepository] Erro ao buscar contagens: {e}")
        return counts

    def get_seasonal_trends(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retorna tendências de procedimentos por mês."""
        query = """
            SELECT TO_CHAR(a.start_time, 'YYYY-MM') AS month,
                   s.name AS service_name,
                   COUNT(a.id) AS count,
                   COALESCE(SUM(a.price), 0) AS revenue
            FROM appointments a
            JOIN services s ON a.service_id = s.id
            WHERE a.start_time IS NOT NULL
            GROUP BY TO_CHAR(a.start_time, 'YYYY-MM'), s.name
            ORDER BY month DESC, count DESC
            LIMIT %s
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
                    return [
                        {
                            "month": row["month"],
                            "service_name": row["service_name"].strip() if row["service_name"] else "",
                            "count": int(row["count"]),
                            "revenue": float(row["revenue"])
                        }
                        for row in rows
                    ]
        except Exception as e:
            print(f"[GithaContextRepository] Erro ao buscar tendências sazonais: {e}")
            return []

    def get_full_context(self) -> GithaContext:
        """Consolida o contexto completo de negócio do Studio Githa."""
        counts = self.get_counts()
        services = self.get_services()
        popular_services = self.get_popular_services(limit=15)
        professionals = self.get_professionals()
        seasonal = self.get_seasonal_trends(limit=20)

        return GithaContext(
            clinic_name="Studio Githa",
            site_url="https://studiogitha.com",
            wp_admin_url="https://studiogitha.com/wp-admin",
            address="Rua Juraci, 88 - Sala 102 - Nova Suíça, Belo Horizonte - MG, CEP 30421-181",
            phone="(31) 9 9169-6979",
            instagram_url="https://www.instagram.com/studiogitha",
            whatsapp_url="https://api.whatsapp.com/send?phone=5531991696979",
            total_services=counts.get("services", len(services)),
            total_clients=counts.get("clients", 0),
            total_appointments=counts.get("appointments", 0),
            services=services,
            popular_services=popular_services,
            professionals=professionals,
            seasonal_trends=seasonal,
            extracted_at=datetime.now().isoformat()
        )
