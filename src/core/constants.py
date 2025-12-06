from enum import Enum
from zoneinfo import ZoneInfo

from src.core.schemas import Error

TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class Role(Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


DEFAULT_ERROR_RESPONSE = {
    400: {
        "description": "Bad request",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "error": {"summary": "Error", "value": {"detail": "Bad request"}},
                }
            }
        },
    },
    401: {
        "description": "Unauthorized",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "invalid_token": {
                        "summary": "Invalid Token",
                        "value": {"detail": "Could not validate credentials"},
                    },
                    "missing_token": {
                        "summary": "Missing Token",
                        "value": {"detail": "Not authenticated"},
                    },
                    "expired_token": {
                        "summary": "Expired Token",
                        "value": {"detail": "Token expired"},
                    },
                }
            }
        },
    },
    403: {
        "description": "Forbidden",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "insufficient_permissions": {
                        "summary": "Insufficient Permissions",
                        "value": {"detail": "Not enough permissions"},
                    },
                    "forbidden": {
                        "summary": "Forbidden",
                        "value": {
                            "detail": "You do not have the permission to access this resource"
                        },
                    },
                }
            }
        },
    },
    404: {
        "description": "Item not found",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "not_found": {
                        "summary": "Resource Not Found",
                        "value": {"detail": "Item not found"},
                    }
                }
            }
        },
    },
    422: {
        "description": "Validation error",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "validation_error": {
                        "summary": "Validation Error",
                        "value": {"detail": "Invalid input parameters"},
                    },
                    "missing_field": {
                        "summary": "Missing Required Field",
                        "value": {"detail": "Required field 'email' is missing"},
                    },
                }
            }
        },
    },
    500: {
        "description": "Internal server error",
        "model": Error,
        "content": {
            "application/json": {
                "examples": {
                    "internal_error": {
                        "summary": "Internal Server Error",
                        "value": {"detail": "Internal server error"},
                    }
                }
            }
        },
    },
}
