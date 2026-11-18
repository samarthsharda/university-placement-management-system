"""Validated request contracts; unknown fields are rejected."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Contract):
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1, max_length=128)


class AcademicUpdate(Contract):
    programme: Literal['CSE','IT','ECE','EEE','MECH']
    graduation_year: int = Field(ge=2020, le=2040)
    cgpa: Decimal = Field(ge=0, le=10, decimal_places=2)
    backlogs: int = Field(ge=0, le=30)
    verified: bool
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=300)


class ContactUpdate(Contract):
    email: str = Field(min_length=3, max_length=150, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


class DriveCreate(Contract):
    title: str = Field(min_length=3, max_length=120)
    programmes: list[Literal['CSE','IT','ECE','EEE','MECH']] = Field(min_length=1, max_length=5)
    graduation_year: int = Field(ge=2020, le=2040)
    minimum_cgpa: Decimal = Field(ge=0, le=10, decimal_places=2)
    maximum_backlogs: int = Field(ge=0, le=30)
    deadline: datetime
    location: str = Field(min_length=2, max_length=120)

    @field_validator('deadline')
    @classmethod
    def future(cls, value):
        if value.tzinfo is None:
            raise ValueError('Include a timezone in the deadline')
        if value <= datetime.now(timezone.utc):
            raise ValueError('Deadline must be in the future')
        return value.astimezone(timezone.utc)


class DriveState(Contract):
    status: Literal['PUBLISHED','CLOSED']
    expected_version: int = Field(ge=1)


class EvaluationRequest(Contract):
    drive_id: str
    student_id: str | None = None


class Submission(Contract):
    resume_version: str | None = None


class ApplicationState(Contract):
    status: Literal['SHORTLISTED','SELECTED','REJECTED','WITHDRAWN']
    expected_version: int = Field(ge=1)


class InterviewCreate(Contract):
    application_id: str
    interviewer: str = Field(min_length=3, max_length=100)
    room: str = Field(min_length=2, max_length=80)
    start: datetime
    end: datetime

    @field_validator('start','end')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Interview times must include a timezone')
        return value.astimezone(timezone.utc)


class OfferCreate(Contract):
    application_id: str
    expires_at: datetime

    @field_validator('expires_at')
    @classmethod
    def future(cls, value):
        if value.tzinfo is None or value <= datetime.now(timezone.utc):
            raise ValueError('Choose a future expiry with a timezone')
        return value.astimezone(timezone.utc)


class OfferDecision(Contract):
    status: Literal['ACCEPTED','DECLINED','REVOKED']
    expected_version: int = Field(ge=1)


class SimulationSettings(Contract):
    notification_outage: bool
