import os
import tempfile

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Dataset, QueryLog
from .serializers import DatasetSerializer, QueryLogSerializer
from .services import schema_utils, sql_guard
from .services import llm_client


class DatasetListView(APIView):
    def get(self, request):
        datasets = Dataset.objects.all().order_by("-uploaded_at")
        return Response(DatasetSerializer(datasets, many=True).data)


class DatasetUploadView(APIView):
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get("name") or os.path.splitext(upload.name)[0]
        table_name = schema_utils.sanitize_table_name(name)

        # Persist to a temp file so pandas can read it regardless of format.
        suffix = os.path.splitext(upload.name)[1] or ".csv"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            df, row_count = schema_utils.load_file_to_table(tmp_path, table_name)
        except Exception as exc:
            return Response({"error": f"Could not parse file: {exc}"}, status=400)
        finally:
            os.unlink(tmp_path)

        schema_json = schema_utils.build_schema_json(df)

        dataset, _created = Dataset.objects.update_or_create(
            table_name=table_name,
            defaults={
                "name": name,
                "original_filename": upload.name,
                "row_count": row_count,
                "schema_json": schema_json,
            },
        )
        return Response(DatasetSerializer(dataset).data, status=201)


class DatasetHistoryView(APIView):
    def get(self, request, dataset_id):
        logs = QueryLog.objects.filter(dataset_id=dataset_id).order_by("created_at")
        return Response(QueryLogSerializer(logs, many=True).data)


class ChatView(APIView):
    """The core agent loop: question -> SQL -> guarded execution -> insight."""

    def post(self, request):
        dataset_id = request.data.get("dataset_id")
        question = (request.data.get("question") or "").strip()

        if not dataset_id or not question:
            return Response({"error": "dataset_id and question are required."}, status=400)

        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            return Response({"error": "Dataset not found."}, status=404)

        schema_block = schema_utils.schema_to_prompt_block(dataset.table_name, dataset.schema_json)
        qualified_question = f"{question}\n\n(Query the table `{dataset.table_name}`.)"

        log = QueryLog(dataset=dataset, question=question)

        try:
            raw_sql = llm_client.generate_sql(qualified_question, schema_block)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=503)

        try:
            safe_sql = sql_guard.validate_select_only(raw_sql)
            safe_sql = sql_guard.enforce_row_limit(safe_sql)
        except sql_guard.SqlRejected as exc:
            log.generated_sql = raw_sql
            log.sql_rejected_reason = exc.reason
            log.save()
            return Response(QueryLogSerializer(log).data, status=200)

        log.generated_sql = safe_sql

        try:
            result_df = schema_utils.run_select(safe_sql)
        except Exception as exc:
            log.sql_rejected_reason = f"Query failed to execute: {exc}"
            log.save()
            return Response(QueryLogSerializer(log).data, status=200)

        records = result_df.to_dict(orient="records")
        log.result_row_count = len(records)
        log.result_preview_json = records[:50]

        insight = llm_client.generate_insight(question, safe_sql, records)
        log.insight_text = insight.get("summary", "")
        log.chart_type = insight.get("chart_type", "table")
        log.chart_config_json = {"x_key": insight.get("x_key"), "y_key": insight.get("y_key")}

        log.save()
        return Response(QueryLogSerializer(log).data, status=200)
