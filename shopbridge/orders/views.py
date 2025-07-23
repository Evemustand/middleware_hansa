from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from .models import WooOrderLog
from decouple import config
import requests
import os
from datetime import datetime

# Hansa API credentials
HANSA_API_URL = config("HANSA_API_URL", default="")
HANSA_USER = config("HANSA_USER", default="")
HANSA_PASS = config("HANSA_PASS", default="")
HOT_IMPORT_FOLDER = config("HOT_IMPORT_FOLDER", default="hansa_exports")

# WooCommerce API credentials
WOO_API_URL = config("WOO_API_URL", default="")
WOO_KEY = config("WOO_CONSUMER_KEY", default="")
WOO_SECRET = config("WOO_CONSUMER_SECRET", default="")


def fetch_product_name_by_sku(sku):
    """
    Fetch product name from WooCommerce REST API using SKU.
    Returns 'UNKNOWN' if not found or API fails.
    """
    if not sku or not WOO_API_URL:
        return "UNKNOWN"
    try:
        url = f"{WOO_API_URL}/products"
        params = {"sku": sku}
        r = requests.get(url, params=params, auth=(WOO_KEY, WOO_SECRET), timeout=5)
        r.raise_for_status()
        products = r.json()
        if products and isinstance(products, list):
            return products[0].get("name", "UNKNOWN")
    except Exception as e:
        print(f"[Woo API Error] Could not fetch name for SKU {sku}: {e}")
    return "UNKNOWN"


class WooWebhookView(APIView):
    """
    Handles WooCommerce webhooks.
    - POST: Processes new WooCommerce order and sends to HansaWorld.
    - GET: Returns a simple status message (for browser testing).
    """
    def get(self, request):
        return Response({
            "status": "running",
            "info": "WooCommerce → Hansa middleware is active. Use POST for webhooks."
        })

    def post(self, request):
        WooOrderLog.objects.create(payload=request.data)

        order_id = str(request.data.get("id") or request.data.get("order_id") or "unknown")
        total = request.data.get("total", "0")
        items = request.data.get("line_items", [])
        quotation_date = datetime.now().strftime("%Y-%m-%d")

        hansa_rows = []
        for i in items:
            product_name = i.get("name") or fetch_product_name_by_sku(i.get("sku"))
            hansa_rows.append({
                "Name": product_name,
                "SKU": i.get("sku", "UNKNOWN"),
                "Qty": i.get("quantity", 0),
                "Price": i.get("price", 0),
            })

        api_payload = {
            "Customer": "SHOP",
            "Reference": order_id,
            "Date": quotation_date,
            "Rows": hansa_rows,
            "Total": total,
        }

        # Try API first
        if HANSA_API_URL:
            try:
                r = requests.post(HANSA_API_URL, json=api_payload,
                                  auth=(HANSA_USER, HANSA_PASS), timeout=10)
                r.raise_for_status()
                return Response({
                    "status": "ok",
                    "method": "api",
                    "hansa_response": r.json()
                })
            except Exception as e:
                print(f"[Hansa API Error] {e} — falling back to Hot Import.")

        # Fallback: Hot Import text file
        try:
            os.makedirs(HOT_IMPORT_FOLDER, exist_ok=True)
            file_path = os.path.join(HOT_IMPORT_FOLDER, f"quotation_{order_id}.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("!Customer\tReference\tDate\tName\tSKU\tQty\tPrice\n")
                for row in hansa_rows:
                    f.write(f"SHOP\t{order_id}\t{quotation_date}\t"
                            f"{row['Name']}\t{row['SKU']}\t{row['Qty']}\t{row['Price']}\n")
            return Response({"status": "ok", "method": "file", "file": file_path})
        except Exception as ex:
            return Response({"status": "failed", "error": str(ex)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def recent_orders(request):
    """Return 5 most recent WooCommerce payloads, with product names fetched if missing."""
    logs = WooOrderLog.objects.all().order_by('-id')[:5]
    data = []
    for log in logs:
        payload = log.payload or {}
        items = payload.get("line_items", [])
        parsed_items = []
        for i in items:
            name = i.get("name") or fetch_product_name_by_sku(i.get("sku"))
            parsed_items.append({
                "name": name,
                "sku": i.get("sku", "UNKNOWN"),
                "quantity": i.get("quantity", 0),
                "price": i.get("price", 0),
            })
        data.append({
            "id": log.id,
            "order_id": payload.get("id") or payload.get("order_id"),
            "total": payload.get("total", 0),
            "items": parsed_items,
            "created_at": log.created_at,
        })
    return Response({"recent_orders": data})


# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from .models import WooOrderLog
# from decouple import config
# import requests
# import os
# from datetime import datetime
# from rest_framework.decorators import api_view
# from orders.models import WooOrderLog
# # Load credentials
# HANSA_API_URL = config("HANSA_API_URL", default="")
# HANSA_USER = config("HANSA_USER", default="")
# HANSA_PASS = config("HANSA_PASS", default="")
# HOT_IMPORT_FOLDER = config("HOT_IMPORT_FOLDER", default="hansa_exports")

# class WooWebhookView(APIView):
#     """
#     Handles WooCommerce webhooks.
#     - POST: Processes new WooCommerce order and sends to HansaWorld.
#     - GET: Returns a simple status message (for browser testing).
#     """
#     def get(self, request):
#         # Simple status check so browser doesn't throw 405
#         return Response({
#             "status": "running",
#             "info": "WooCommerce → Hansa middleware is active. Use POST for webhooks."
#         })

#     def post(self, request):
#         # Log raw WooCommerce order
#         WooOrderLog.objects.create(payload=request.data)

#         # Extract order data
#         order_id = str(request.data.get("id") or request.data.get("order_id") or "unknown")
#         total = request.data.get("total", "0")
#         items = request.data.get("line_items", [])
#         quotation_date = datetime.now().strftime("%Y-%m-%d")

#         # Build Hansa rows
#         hansa_rows = [
#             {
#             "Name": i.get("name", "UNKNOWN"),
#             "SKU": i.get("sku", "UNKNOWN"),
#             "SKU": i.get("sku", "UNKNOWN"),
#               "Qty": i.get("quantity", 0), 
#               "Price": i.get("price", 0)
              
#               }
#             for i in items
#         ]

#         api_payload = {
#             "Customer": "SHOP",
#             "Reference": order_id,
#             "Date": quotation_date,
#             "Rows": hansa_rows,
#             "Total": total,
#         }

#         # Try Hansa API
#         if HANSA_API_URL:
#             try:
#                 response = requests.post(
#                     HANSA_API_URL,
#                     json=api_payload,
#                     auth=(HANSA_USER, HANSA_PASS),
#                     timeout=10
#                 )
#                 response.raise_for_status()
#                 return Response({
#                     "status": "ok",
#                     "method": "api",
#                     "hansa_response": response.json()
#                 })
#             except Exception as e:
#                 print(f"[Hansa API Error] {e} — falling back to Hot Import.")

#         # Fallback: Hot Import text file
#         try:
#             os.makedirs(HOT_IMPORT_FOLDER, exist_ok=True)
#             file_path = os.path.join(HOT_IMPORT_FOLDER, f"quotation_{order_id}.txt")
#             with open(file_path, "w", encoding="utf-8") as f:
#                 f.write("!Customer\tReference\tDate\tSKU\tQty\tPrice\n")
#                 for row in hansa_rows:
#                     f.write(f"SHOP\t{order_id}\t{quotation_date}\t{row['SKU']}\t{row['Qty']}\t{row['Price']}\n")

#             return Response({
#                 "status": "ok",
#                 "method": "file",
#                 "file": file_path
#             })

#         except Exception as ex:
#             return Response({"status": "failed", "error": str(ex)},
#                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# @api_view(['GET'])
# def recent_orders(request):
#     """Returns the 5 most recent WooCommerce webhook payloads for testing."""
#     logs = WooOrderLog.objects.all().order_by('-id')[:5]
#     data = [
#         {
#             "id": log.id,
#             "payload": log.payload,
#             "created_at": log.created_at,
#         }
#         for log in logs
#     ]
#     return Response({"recent_orders": data})



# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from .models import WooOrderLog
# from decouple import config
# import requests
# import os
# from datetime import datetime
# import logging

# # Setup logging (optional, to track events/errors in console)
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# # Load credentials and paths securely from .env
# HANSA_API_URL = config("HANSA_API_URL", default="")
# HANSA_USER = config("HANSA_USER", default="")
# HANSA_PASS = config("HANSA_PASS", default="")
# HOT_IMPORT_FOLDER = config("HOT_IMPORT_FOLDER", default="hansa_exports")

# class WooWebhookView(APIView):
#     """
#     Handles WooCommerce webhooks: Creates a quotation in HansaWorld.
#     - Tries Hansa API first (if configured).
#     - Falls back to Hot Import text file if API fails/unavailable.
#     """

#     def post(self, request):
#         # Log full payload for debugging/audit
#         WooOrderLog.objects.create(payload=request.data)
#         logging.info(f"Received WooCommerce order: {request.data}")

#         # Extract core order details
#         order_id = str(request.data.get("id") or request.data.get("order_id") or "unknown")
#         total = request.data.get("total", "0")
#         items = request.data.get("line_items", [])
#         quotation_date = datetime.now().strftime("%Y-%m-%d")

#         # Prepare line items for Hansa
#         hansa_rows = []
#         for item in items:
#             hansa_rows.append({
#                 "SKU": item.get("sku", "UNKNOWN"),
#                 "Qty": item.get("quantity", 0),
#                 "Price": item.get("price", 0)
#             })

#         # Build API payload
#         api_payload = {
#             "Customer": "SHOP",  # Default customer for online sales
#             "Reference": order_id,
#             "Date": quotation_date,
#             "Rows": hansa_rows,
#             "Total": total
#         }

#         # Attempt API push first
#         if HANSA_API_URL:
#             try:
#                 response = requests.post(
#                     HANSA_API_URL,
#                     json=api_payload,
#                     auth=(HANSA_USER, HANSA_PASS),
#                     timeout=10
#                 )
#                 response.raise_for_status()
#                 logging.info(f"Hansa API success: {response.json()}")
#                 return Response({
#                     "status": "ok",
#                     "method": "api",
#                     "hansa_response": response.json()
#                 })
#             except Exception as e:
#                 logging.error(f"Hansa API error: {e} — switching to Hot Import fallback.")

#         # Fallback: Hot Import text file
#         try:
#             os.makedirs(HOT_IMPORT_FOLDER, exist_ok=True)
#             filename = f"quotation_{order_id}.txt"
#             file_path = os.path.join(HOT_IMPORT_FOLDER, filename)

#             with open(file_path, "w", encoding="utf-8") as f:
#                 # Hansa expects a header row (tab-delimited)
#                 f.write("!Customer\tReference\tDate\tSKU\tQty\tPrice\n")
#                 for row in hansa_rows:
#                     f.write(
#                         f"SHOP\t{order_id}\t{quotation_date}\t"
#                         f"{row['SKU']}\t{row['Qty']}\t{row['Price']}\n"
#                     )

#             logging.info(f"Hansa Hot Import file created: {file_path}")
#             return Response({
#                 "status": "ok",
#                 "method": "file",
#                 "file": file_path
#             })

#         except Exception as ex:
#             logging.error(f"Failed to write Hot Import file: {ex}")
#             return Response(
#                 {"status": "failed", "error": str(ex)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
