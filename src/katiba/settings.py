from dotenv import find_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",  # ignore .env keys that don't map to a field
    )

    neo4j_http_port: int
    neo4j_bolt_port: int
    neo4j_user: str
    neo4j_password: SecretStr  # pydantic won't accidentally print this in logs
    neo4j_plugins: str
    neo4j_heap_initial_size: str
    neo4j_heap_max_size: str
    neo4j_pagecache_size: str


class NeoDashSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neodash_port: int
    neodash_standalone: bool
    neodash_sso_enabled: bool


class GeminiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr
    gemini_model: str


# Instantiate once — import these singletons rather than re-instantiating per script
neo4j_settings = Neo4jSettings()
neodash_settings = NeoDashSettings()
gemini_settings = GeminiSettings()
