from django.db import models

from posthog.models.utils import UUIDTModel


class TicketAssignment(UUIDTModel):
    ticket = models.OneToOneField("conversations.Ticket", on_delete=models.CASCADE, related_name="assignment")
    user = models.ForeignKey("posthog.User", null=True, on_delete=models.CASCADE)
    role_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "posthog_conversations_ticket_assignment"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user_id__isnull=False, role_id__isnull=True)
                    | models.Q(user_id__isnull=True, role_id__isnull=False)
                ),
                name="exactly_one_assignee_type",
            ),
        ]
