from rest_framework import serializers

from .models import Dataset, QueryLog


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ["id", "name", "table_name", "row_count", "schema_json", "uploaded_at"]


class QueryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryLog
        fields = [
            "id", "dataset", "question", "generated_sql", "sql_rejected_reason",
            "result_row_count", "result_preview_json", "chart_type",
            "chart_config_json", "insight_text", "created_at",
        ]
