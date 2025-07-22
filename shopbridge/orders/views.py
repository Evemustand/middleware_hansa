from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import WooOrderLog
from decouple import config
import requests
import os
from datetime import datetime

# Load credentials and paths from .env (or defaults)
HANSA_API_URL = config("HANSA_API_URL", default="")
HANSA_USER = config("HANSA_USER", default="")
HANSA_PASS = config("HANSA_PASS", default="")
HOT_IMPORT_FOLDER = config("HOT_IMPORT_FOLDER", default="hansa_exports")

class WooWebhookView(APIView):
    """
    Receives WooCommerce order webhooks and creates a Quotation in HansaWorld.
    Tries API first, falls back to Hot Import text file if API is unavailable.
    """

    def post(self, request):
        # Log the raw WooCommerce order for debugging/auditing
        WooOrderLog.objects.create(payload=request.data)

        # Extract order details from WooCommerce payload
        order_id = str(request.data.get("id") or request.data.get("order_id") or "unknown")
        total = request.data.get("total", "0")
        items = request.data.get("line_items", [])

        quotation_date = datetime.now().strftime("%Y-%m-%d")

        # Prepare rows for Hansa
        hansa_rows = []
        for i in items:
            hansa_rows.append({
                "SKU": i.get("sku", "UNKNOWN"),
                "Qty": i.get("quantity", 0),
                "Price": i.get("price", 0)
            })

        # Build API payload
        api_payload = {
            "Customer": "SHOP",  # Default customer for website orders
            "Reference": order_id,
            "Date": quotation_date,
            "Rows": hansa_rows,
            "Total": total
        }

        # Try to send via Hansa API (if configured)
        if HANSA_API_URL:
            try:
                response = requests.post(
                    HANSA_API_URL,
                    json=api_payload,
                    auth=(HANSA_USER, HANSA_PASS),
                    timeout=10
                )
                response.raise_for_status()
                return Response({
                    "status": "ok",
                    "method": "api",
                    "hansa_response": response.json()
                })
            except Exception as e:
                # Log error and fall back to Hot Import
                print(f"[Hansa API Error] {e} — falling back to Hot Import method.")

        # Fallback: Write a Hansa-compatible text file for Hot Import
        try:
            os.makedirs(HOT_IMPORT_FOLDER, exist_ok=True)
            filename = f"quotation_{order_id}.txt"
            file_path = os.path.join(HOT_IMPORT_FOLDER, filename)

            # Tab-delimited format for Hansa
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("!Customer\tReference\tDate\tSKU\tQty\tPrice\n")
                for row in hansa_rows:
                    f.write(
                        f'SHOP\t{order_id}\t{quotation_date}\t'
                        f'{row["SKU"]}\t{row["Qty"]}\t{row["Price"]}\n'
                    )

            return Response({
                "status": "ok",
                "method": "file",
                "file": file_path
            })

        except Exception as ex:
            return Response(
                {"status": "failed", "error": str(ex)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
