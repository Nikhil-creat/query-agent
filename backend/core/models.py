from django.db import models


class Dataset(models.Model):
    """One uploaded CSV/XLSX file, loaded into its own SQLite table so the
    agent can query it with real SQL instead of re-parsing pandas each time.
    """

    name = models.CharField(max_length=255)
    table_name = models.CharField(max_length=64, unique=True)  # sanitized, sql-safe
    original_filename = models.CharField(max_length=255)
    row_count = models.IntegerField(default=0)
    schema_json = models.JSONField(default=dict)  # {col: {"dtype": ..., "sample": [...]}}
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.row_count} rows)"


class QueryLog(models.Model):
    """One turn of the conversation: the question asked, the SQL the model
    generated for it, and what came back. Kept even when a query fails --
    a wrong query the student can show and explain is still useful.
    """

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="queries")
    question = models.TextField()
    generated_sql = models.TextField(blank=True)
    sql_rejected_reason = models.TextField(blank=True)  # set if sql_guard blocked it
    result_row_count = models.IntegerField(null=True, blank=True)
    result_preview_json = models.JSONField(default=list, blank=True)  # first N rows
    chart_type = models.CharField(max_length=20, blank=True)  # bar/line/pie/table/none
    chart_config_json = models.JSONField(default=dict, blank=True)
    insight_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Q: {self.question[:50]}"
