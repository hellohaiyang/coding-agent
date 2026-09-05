from pydantic import BaseModel, ConfigDict, Field, field_validator

from Agent.config.config import Config


class ToolArguments(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True
    )


class BashArguments(ToolArguments):
    command: str = Field(min_length=1, max_length=20000)
    timeout: int = Field(
        default=30,
        ge=1,
        le=Config.sandbox_max_timeout,
    )

    @field_validator("command")
    @classmethod
    def command_not_blank(cls, value):
        if not value.strip():
            raise ValueError("command is none")
        return value


class ReadArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    offset: int = Field(default=1, ge=1)
    limit: int = Field(default=200, ge=1, le=2000)


class WriteArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1000000)


class EditArguments(ToolArguments):
    path: str = Field(min_length=1, max_length=4096)
    old_text: str = Field(min_length=1, max_length=1000000)
    new_text: str = Field(max_length=1000000)


TOOL_ARGUMENT_MODELS = {
    "bash": BashArguments,
    "read": ReadArguments,
    "write": WriteArguments,
    "edit": EditArguments,
}
