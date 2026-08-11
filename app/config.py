from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    app_name: str = "F1 Data API"
    app_env: str = "production"
    api_version: str = "1.1.0"

    # DB connection: use DATABASE_URL, or DB_* fields, optionally with AWS Secrets Manager.
    database_url: str | None = None
    db_host: str 
    db_port: int 
    db_name: str 
    db_user: str  
    db_password: str 
    aws_region: str = "ap-northeast-2"
    aws_db_secret_arn: str | None = None
    rds_ca_bundle: str 

    sql_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle_seconds: int = 1800

    fastf1_cache_dir: str = "/var/cache/f1-api/fastf1"
    cors_origins: str 

    # Startup/collector behavior.
    collect_seasons: str = "2026"
    collect_after_start_minutes: int = 240
    collector_lookback_days: int = 365

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def collection_season_list(self) -> list[int]:
        return sorted({int(x.strip()) for x in self.collect_seasons.split(",") if x.strip()})

    @property
    def cache_path(self) -> Path:
        return Path(self.fastf1_cache_dir).expanduser().resolve()

    @cached_property
    def db_credentials(self) -> dict[str, str | int]:
        if not self.aws_db_secret_arn:
            return {
                "host": self.db_host,
                "port": self.db_port,
                "dbname": self.db_name,
                "username": self.db_user,
                "password": self.db_password or "",
            }

        # On EC2, boto3 automatically uses the instance IAM role. Do not put an AWS access key in .env.
        import boto3

        client = boto3.client("secretsmanager", region_name=self.aws_region)
        response = client.get_secret_value(SecretId=self.aws_db_secret_arn)
        secret = json.loads(response["SecretString"])
        return {
            "host": secret.get("host") or self.db_host,
            "port": int(secret.get("port") or self.db_port),
            "dbname": secret.get("dbname") or secret.get("database") or self.db_name,
            "username": secret.get("username") or self.db_user,
            "password": secret.get("password") or self.db_password or "",
        }

    @cached_property
    def sqlalchemy_url(self) -> URL | str:
        if self.database_url:
            return self.database_url
        c = self.db_credentials
        return URL.create(
            "mysql+pymysql",
            username=str(c["username"]),
            password=str(c["password"]),
            host=str(c["host"]),
            port=int(c["port"]),
            database=str(c["dbname"]),
            query={"charset": "utf8mb4"},
        )

    @property
    def db_connect_args(self) -> dict:
        args: dict = {
            "connect_timeout": 10,
            "read_timeout": 30,
            "write_timeout": 30,
        }
        if self.rds_ca_bundle:
            ca = Path(self.rds_ca_bundle).expanduser().resolve()
            args.update(
                ssl_ca=str(ca),
                ssl_verify_cert=True,
                ssl_verify_identity=True,
            )
        return args
    @model_validator(mode="after")
    def validate_production_security(self):
        if self.app_env == "production":
            if not self.rds_ca_bundle:
                raise ValueError(
                    "RDS_CA_BUNDLE is required in production"
                )

            if self.sql_echo:
                raise ValueError(
                    "SQL_ECHO must be false in production"
                )

        return self


settings = Settings()
