from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A login that belongs to exactly one org (tenant).

    `org_id` is the only source of a request's tenant: TenantMiddleware reads
    it from request.user, never from anything the client sends.

    The users table itself is not RLS-protected: login has to look a user up
    before we know which org they are in.
    """

    org_id = models.CharField(max_length=16, db_index=True)

    # Prompted for by `createsuperuser`, so no user can be created org-less.
    REQUIRED_FIELDS = ["org_id"]

    class Meta:
        db_table = "users"
