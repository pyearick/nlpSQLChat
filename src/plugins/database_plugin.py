# database_plugin.py
# This is a revised version of the database_plugin.py based on our earlier discussion.
# Key improvements:
# - Introduced a table_info dictionary to hold table metadata (descriptions, key columns, usage) in a structured way.
# - Built the kernel_function description dynamically from the dictionary for conciseness, reducing overall prompt size and token usage.
# - Condensed guidelines, examples, and best practices to essential information, removing redundant verbose sections.
# - Maintained critical validation, export features, and helper functions.
# - Balanced table handling by emphasizing equal treatment in guidelines, with dynamic joins for comprehensive queries.
# - Added parsing hints in guidelines for "Tell me about [blank]" style queries to dynamically select tables without hard-coding.

import logging
import csv
import os
from datetime import datetime
from typing import Annotated, List, Union
from pathlib import Path

import pyodbc
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from src.database.service import Database

logger = logging.getLogger(__name__)

# Dictionary for table metadata to optimize prompt construction
table_info = {
    "pmsalespbi": {
        "description": "ACTUAL INVOICE SALES DATA by customer (PRIMARY SALES TABLE).",
        "key_columns": "CaptureDate, Company, CustomerGroup, CustomerName, Product, ProductCategoryID, ProdDivID, ProdGroupID, ProdGroupDes, Quantity, Sales, Cost, Margin, InvMonth, InvQuarter, InvWeek, InvYear, InvDate",
        "usage": "Use for sales to customers, revenue, margins, product categories."
    },
    "rightScore_results": {
        "description": "PRODUCT SCORING & INVENTORY OPTIMIZATION DATA (ANALYTICAL TABLE).",
        "key_columns": "CaptureDate, LastUpdated, Product, ProdGroupDes, Flag3Year, Flag1Year, ForecastScore, VIOScore, CompScore, eBayScore, MSRPScore, DistScore, ProfitScore, StockScore, OverallScore",
        "usage": "Use for inventory optimization, product performance, dead stock (higher scores = better; Flag3Year/Flag1Year for new products)."
    },
    "ebayWT": {
        "description": "eBay auction listings (LARGE TABLE - 2M+ records). Market pricing data.",
        "key_columns": "OEAN, UnitPrice (nvarchar - use TRY_CONVERT(decimal(10,2), UnitPrice)), Quantity, CaptureDate, SellerID, Title, EndTime",
        "usage": "Use for market pricing; filter non-numeric UnitPrice."
    },
    "ebayWT_NF": {
        "description": "eBay auctions for parts NOT in our inventory (competitive analysis).",
        "key_columns": "OEAN, DeltaSold, SoldPrice, SoldDate",
        "usage": "Use for competitive sales indicators."
    },
    "ebayNF_SupplierMatch": {
        "description": "Competitor parts with supplier matching data.",
        "key_columns": "OEAN, SupplierName, SupplierPrice, PartDescription",
        "usage": "Supplier fields may be NULL; use for competitor-supplier matches."
    },
    "OEPriceBookPBI": {
        "description": "OE MANUFACTURER PRICING DATA from Standard Motor Products (monthly updates).",
        "key_columns": "BatchID, Make, [Part Number], [Part Description], [Dealer List Price], [Date Last Price Change], [Supperseded Flag], [Superseded Part Number], [Country ID], Notes, Status",
        "usage": "Use brackets for columns; for MSRP, supersessions, price history."
    },
    "InternetCompData": {
        "description": "COMPETITOR PRICING & AVAILABILITY from web scraping (competitive intelligence).",
        "key_columns": "[File_Name], [Record_ID], [OEAN], [Competitor Name], [Description], [Price], [Availability], [Addtl OE Numbers], [Competitor Part Number]",
        "usage": "Use brackets for columns; for competitive pricing, availability."
    },
    "Suppliers": {
        "description": "SUPPLIER SOURCING OPTIONS from MongoDB-processed Excel catalogs (200+ supplier files).",
        "key_columns": "[OEAN], [Name], [collection]",
        "usage": "collection: file path + sheet; for sourcing, procurement."
    },
    "rightStock_ProductOEs": {
        "description": "PRODUCT-TO-OEAN CROSS-REFERENCE (enables product-level intelligence).",
        "key_columns": "[CaptureDate], [Product], [OE]",
        "usage": "Map products to OEANs for joins across tables."
    }
}

# Construct concise table listing from dictionary
tables_section = "IMPORTANT: Only query these approved production tables:\n"
for table, info in table_info.items():
    tables_section += f"- {table}: {info['description']} Key columns: {info['key_columns']}. {info['usage']}\n"

# Condensed guidelines and examples
guidelines_section = """
SEARCH STRATEGY:
1. Customer searches: UPPER(CustomerName) LIKE '%[TERM]%'
2. Product searches: UPPER(Product) LIKE '%[TERM]%' OR UPPER(ProdGroupDes) LIKE '%[CATEGORY]%'
3. OEAN searches: Exact match on OEAN/[Part Number]/[OE]
4. For "Tell me about [blank]": Parse [blank] as OEAN/product/customer, select relevant tables via rightStock_ProductOEs mapping, use joins for comprehensive view.
5. No results: Suggest broader terms or use suggest_similar_matches.

TABLE USAGE GUIDELINES:
- Sales/revenue/customers: pmsalespbi
- Performance/inventory/dead stock: rightScore_results (e.g., WHERE StockScore <= 2)
- Market pricing/eBay: ebayWT (convert UnitPrice)
- MSRP/supersessions: OEPriceBookPBI
- Competitors: InternetCompData
- Suppliers/sourcing: Suppliers
- Mapping: rightStock_ProductOEs for product-OEAN joins

CRITICAL FIELD MAPPING & DATA TYPES:
- OEAN variants: OEAN, [OEAN], [Part Number], [OE]
- Product: Product
- ebayWT.UnitPrice: TRY_CONVERT(decimal(10,2), UnitPrice); filter IS NOT NULL
- Use brackets for columns with spaces/brackets.

JOIN PATTERNS FOR 360° ANALYSIS:
- For OEAN [X]: SELECT ... FROM rightStock_ProductOEs p JOIN pmsalespbi s ON p.[Product]=s.Product JOIN OEPriceBookPBI o ON p.[OE]=o.[Part Number] ... WHERE p.[OE]='[X]'
- For product [Y]: SELECT ... FROM rightStock_ProductOEs p JOIN rightScore_results r ON p.[Product]=r.Product ... WHERE p.[Product]='[Y]'
- Competitive: JOIN InternetCompData i ON [OEAN]=i.[OEAN]
- Suppliers: JOIN Suppliers s ON [OEAN]=s.[OEAN]
- eBay: LEFT JOIN ebayWT e ON [OEAN]=e.OEAN

QUERY BEST PRACTICES:
- Use LIKE with % for text searches (case-insensitive via UPPER).
- Use TOP N for large results (>100 rows).
- SQL Server syntax (TOP N, not LIMIT).
- Handle NULLs; aggregate with SUM/AVG/COUNT.
- For comprehensive queries (e.g., OEAN/product intel), join multiple tables equally without prioritizing one.
- Forbidden tables: Patterns like _backup, temp_, test rejected in code.

When asking about specific OEAN/product, use rightStock_ProductOEs for mapping, then join relevant tables for full intel (sales, scores, MSRP, competition, suppliers, eBay).
"""

# Combined description for kernel_function
query_description = (
    "Query the CRPAF database using SQL Server syntax. "
    + tables_section
    + guidelines_section
)


class DatabasePlugin:
    """DatabasePlugin with smart result handling for large datasets."""

    def __init__(self, db: Database, max_display_rows: int = 100, export_dir: str = "C:/Logs/VoiceSQL/exports") -> None:
        self.db = db
        self.max_display_rows = max_display_rows
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _estimate_row_count(self, query: str) -> int:
        """Estimate the number of rows a query will return"""
        try:
            query_upper = query.strip().upper()

            if query_upper.startswith('SELECT *') and 'WHERE' not in query_upper and 'JOIN' not in query_upper:
                parts = query_upper.split()
                if len(parts) >= 4 and parts[1] == '*' and parts[2] == 'FROM':
                    table_name = parts[3].strip()
                    count_query = f"SELECT COUNT(*) FROM {table_name}"
                    result = self.db.query(count_query)
                    if result and not isinstance(result, str):
                        return result[0][0]

            count_query = query
            if 'ORDER BY' in query_upper:
                order_by_pos = query_upper.rfind('ORDER BY')
                count_query = query[:order_by_pos].strip()

            count_query = f"SELECT COUNT(*) FROM ({count_query}) AS count_subquery"
            result = self.db.query(count_query)

            if result and not isinstance(result, str):
                return result[0][0]

        except Exception as e:
            logger.warning(f"Could not estimate row count: {e}")

        return -1

    def _export_to_file(self, query: str, file_format: str = 'csv') -> str:
        """Export query results to a file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"query_export_{timestamp}.{file_format}"
            filepath = self.export_dir / filename

            result = self.db.query(query)
            if isinstance(result, str):
                return f"Error executing query for export: {result}"

            if not result:
                return f"Query executed successfully but returned no data to export."

            if hasattr(result[0], 'cursor_description') and result[0].cursor_description:
                column_names = [desc[0] for desc in result[0].cursor_description]
            else:
                try:
                    first_row = result[0]
                    column_count = len(first_row)
                    column_names = [f"Column_{i + 1}" for i in range(column_count)]
                except:
                    column_names = ["Data"]

            if file_format.lower() == 'csv':
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(column_names)
                    for row in result:
                        if hasattr(row, '__iter__') and not isinstance(row, (str, bytes)):
                            row_values = [str(cell) if cell is not None else '' for cell in row]
                        else:
                            row_values = [str(row) if row is not None else '']
                        writer.writerow(row_values)

            elif file_format.lower() == 'txt':
                with open(filepath, 'w', encoding='utf-8') as txtfile:
                    txtfile.write('\t'.join(column_names) + '\n')
                    for row in result:
                        if hasattr(row, '__iter__') and not isinstance(row, (str, bytes)):
                            row_values = [str(cell) if cell is not None else '' for cell in row]
                        else:
                            row_values = [str(row) if row is not None else '']
                        txtfile.write('\t'.join(row_values) + '\n')

            row_count = len(result)
            return (f"Exported {row_count:,} rows to {file_format.upper()} format. "
                    f"File: {filename} "
                    f"Ready for download from server.")

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return f"Export failed: {e}"

    @kernel_function(
        name="query",
        description=query_description
    )
    def query(self, query: Annotated[str, "The SQL query"]) -> Annotated[
        Union[List[pyodbc.Row], str], "The rows returned or a message"]:
        logger.info(f"Running database plugin with query: {query}")

        query_upper = query.upper()
        forbidden_patterns = [
            '_BACKUP', '_TEMP', '_STAGING', '_WORK',
            'TEMP_', 'BACKUP_', 'OLD_', 'ARCHIVE_',
            'TEST', 'DEV', 'INTERMEDIATE'
        ]

        for pattern in forbidden_patterns:
            if pattern in query_upper:
                error_msg = f"Query rejected: Contains forbidden table pattern '{pattern}'. Only approved production tables are allowed."
                logger.warning(error_msg)
                return error_msg

        estimated_rows = self._estimate_row_count(query)

        if estimated_rows > self.max_display_rows:
            return (f"WARNING: This query will return approximately {estimated_rows:,} rows, "
                    f"which is too large to display. Consider:\n"
                    f"1. Adding 'TOP {self.max_display_rows}' to see a sample\n"
                    f"2. Adding WHERE conditions to filter the data\n"
                    f"3. Ask me to 'export the full results to CSV file' if you need all data\n\n"
                    f"Would you like me to show just the first {self.max_display_rows} rows instead?")

        result = self.db.query(query)

        if isinstance(result, list) and len(result) > self.max_display_rows:
            return (f"Query returned {len(result):,} rows (showing first {self.max_display_rows}):\n\n" +
                    str(result[:self.max_display_rows]) +
                    f"\n\n... and {len(result) - self.max_display_rows:,} more rows. "
                    f"Ask me to 'export full results to CSV' if you need all data.")

        return result

    @kernel_function(
        name="suggest_similar_matches",
        description=(
            "When a customer or product search returns no results, use this to find similar matches. "
            "Helps users discover the correct customer/product names in the database."
        )
    )
    def suggest_similar_matches(self,
                                search_term: Annotated[str, "The customer or product name that returned no results"]) -> \
    Annotated[str, "Suggested similar matches"]:
        """Find similar customer or product names when exact search fails"""
        try:
            customer_query = f"SELECT DISTINCT TOP 10 CustomerName FROM pmsalespbi WHERE UPPER(CustomerName) LIKE '%{search_term.upper()}%' ORDER BY CustomerName"
            customer_result = self.db.query(customer_query)

            product_query = f"SELECT DISTINCT TOP 10 Product FROM pmsalespbi WHERE UPPER(Product) LIKE '%{search_term.upper()}%' ORDER BY Product"
            product_result = self.db.query(product_query)

            suggestions = []

            if customer_result and not isinstance(customer_result, str) and len(customer_result) > 0:
                customer_names = [row[0] for row in customer_result]
                suggestions.append(f"Similar customer names found: {', '.join(customer_names)}")

            if product_result and not isinstance(product_result, str) and len(product_result) > 0:
                product_names = [row[0] for row in product_result]
                suggestions.append(f"Similar product names found: {', '.join(product_names)}")

            if suggestions:
                return "I found these similar matches:\n" + "\n".join(
                    suggestions) + "\n\nWould you like me to search for any of these instead?"
            else:
                return f"No similar matches found for '{search_term}'. Try using fewer letters or check the spelling."

        except Exception as e:
            logger.error(f"Error in suggest_similar_matches: {e}")
            return f"Error searching for similar matches: {e}"

    @kernel_function(
        name="export_query_to_csv",
        description="Export query results to a CSV file."
    )
    def export_query_to_csv(self, query: Annotated[str, "The SQL query to export"]) -> Annotated[
        str, "Export status message"]:
        logger.info(f"Exporting query to CSV: {query}")
        return self._export_to_file(query, 'csv')

    @kernel_function(
        name="export_query_to_txt",
        description=(
            "Export query results to a tab-delimited text file. "
            "Alternative to CSV export for users who prefer text format."
        )
    )
    def export_query_to_txt(self, query: Annotated[str, "The SQL query to export"]) -> Annotated[
        str, "Export status message"]:
        logger.info(f"Exporting query to TXT: {query}")
        return self._export_to_file(query, 'txt')

    @kernel_function(
        name="get_table_size",
        description=(
            "Get the approximate number of rows in a table to help users understand data size before querying."
        )
    )
    def get_table_size(self, table_name: Annotated[str, "Name of the table"]) -> Annotated[
        str, "Table size information"]:
        logger.info(f"Getting size for table: {table_name}")

        try:
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            result = self.db.query(count_query)

            if isinstance(result, str):
                return f"Error getting table size: {result}"

            if result:
                row_count = result[0][0]
                logger.info(
                    f"Table '{table_name}' contains {row_count:,} rows. WARNING: Very large - Use specific WHERE conditions or TOP N")

                if row_count > 1000000:
                    size_context = "VERY LARGE - Use specific WHERE conditions or TOP N"
                elif row_count > 100000:
                    size_context = "LARGE - Consider using TOP N for faster queries"
                elif row_count > 10000:
                    size_context = "MEDIUM - Good for most queries"
                else:
                    size_context = "SMALL - Fast for any query"

                return f"Table '{table_name}' contains {row_count:,} rows. {size_context}"
            else:
                return f"Table '{table_name}' appears to be empty or doesn't exist."

        except Exception as e:
            logger.error(f"Error getting table size: {e}")
            return f"Error getting table size: {e}"