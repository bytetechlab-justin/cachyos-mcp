import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

PROJECT = Path(__file__).resolve().parents[2]
GROUPS = {
    "system",
    "hardware",
    "processes",
    "network",
    "packages",
    "systemd",
    "journal",
    "filesystem",
    "kde",
    "development",
    "privileged",
}


class Settings(BaseModel):
    _policy_path: Path = PrivateAttr(default=PROJECT / "config/settings.toml")
    model_config = ConfigDict(extra="forbid", strict=True)
    allowed_project_directories: list[str] = Field(default_factory=lambda: ["~/Projects"])
    allowed_writable_directories: list[str] = Field(
        default_factory=lambda: ["~/Projects", "~/.config", "~/.local"]
    )
    enabled_tool_groups: list[str] = Field(default_factory=lambda: sorted(GROUPS))
    privileged_enabled: bool = False
    allowed_packages: list[str] = Field(default_factory=lambda: ["blender"])
    allowed_services: list[str] = Field(default_factory=lambda: ["bluetooth.service"])
    max_command_timeout: int = Field(default=30, ge=1, le=3600)
    max_output_size: int = Field(default=65536, ge=1024, le=1048576)
    max_file_size: int = Field(default=262144, ge=1024, le=1048576)
    logging_level: str = "INFO"
    log_directory: str = str(PROJECT / ".state")
    log_max_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    log_backups: int = Field(default=3, ge=1, le=10)

    @field_validator("enabled_tool_groups")
    @classmethod
    def groups(cls, value):
        if set(value) - GROUPS:
            raise ValueError("Unknown tool group")
        return value

    @field_validator("logging_level")
    @classmethod
    def level(cls, value):
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid logging level")
        return value

    @field_validator("allowed_project_directories", "allowed_writable_directories")
    @classmethod
    def roots(cls, values):
        for value in values:
            p = Path(value).expanduser()
            if not p.is_absolute() or ".." in p.parts or not p.is_relative_to(Path.home()):
                raise ValueError("Write roots must be absolute directories inside your home")
            if p == Path.home():
                raise ValueError("Entire home is not a permitted write root")
        return values


def load(path: Path | None = None) -> Settings:
    policy_path = (path or PROJECT / "config/settings.toml").expanduser().absolute()
    with policy_path.open("rb") as stream:
        settings = Settings.model_validate(tomllib.load(stream))
    settings._policy_path = policy_path
    return settings
