from enum import Enum

from pydantic import BaseModel, Field


class WebhookType(str, Enum):
    feishu = "feishu"
    dingtalk = "dingtalk"
    wecom = "wecom"
    slack = "slack"
    generic = "generic"


class TriggerConfig(BaseModel):
    min_severity: str = "warning"
    on_category: list[str] = Field(default_factory=list)
    on_rule_ids: list[str] = Field(default_factory=list)
    on_review_started: bool = False
    on_review_complete: bool = True
    on_finding_created: bool = False


class WebhookConfig(BaseModel):
    name: str
    enabled: bool = True
    type: WebhookType
    url: str
    secret: str = ""
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: str = ""
    template: str = ""
    triggers: TriggerConfig = Field(default_factory=TriggerConfig)
