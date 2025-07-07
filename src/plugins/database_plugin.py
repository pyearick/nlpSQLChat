# Fixed database_plugin.py export methods

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
            # Convert the query to a COUNT query
            query_upper = query.strip().upper()

            # Simple heuristic: if it's a basic SELECT * FROM table, get exact count
            if query_upper.startswith('SELECT *') and 'WHERE' not in query_upper and 'JOIN' not in query_upper:
                # Extract table name for direct count
                parts = query_upper.split()
                if len(parts) >= 4 and parts[1] == '*' and parts[2] == 'FROM':
                    table_name = parts[3].strip()
                    count_query = f"SELECT COUNT(*) FROM {table_name}"
                    result = self.db.query(count_query)
                    if result and not isinstance(result, str):
                        return result[0][0]

            # For complex queries, try to wrap in COUNT
            # Remove ORDER BY clause for counting
            count_query = query
            if 'ORDER BY' in query_upper:
                order_by_pos = query_upper.rfind('ORDER BY')
                count_query = query[:order_by_pos].strip()

            # Wrap in COUNT subquery
            count_query = f"SELECT COUNT(*) FROM ({count_query}) AS count_subquery"
            result = self.db.query(count_query)

            if result and not isinstance(result, str):
                return result[0][0]

        except Exception as e:
            logger.warning(f"Could not estimate row count: {e}")

        return -1  # Unknown

    def _export_to_file(self, query: str, file_format: str = 'csv') -> str:
        """Export query results to a file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"query_export_{timestamp}.{file_format}"
            filepath = self.export_dir / filename

            # Execute the query
            result = self.db.query(query)
            if isinstance(result, str):
                return f"Error executing query for export: {result}"

            if not result:
                return f"Query executed successfully but returned no data to export."

            # Get column information from the first row
            if hasattr(result[0], 'cursor_description') and result[0].cursor_description:
                # Get column names from cursor description
                column_names = [desc[0] for desc in result[0].cursor_description]
            else:
                # Fallback: try to get column count and create generic names
                try:
                    first_row = result[0]
                    column_count = len(first_row)
                    column_names = [f"Column_{i + 1}" for i in range(column_count)]
                except:
                    column_names = ["Data"]

            if file_format.lower() == 'csv':
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)

                    # Write headers
                    writer.writerow(column_names)

                    # Write data rows
                    for row in result:
                        # Convert row to list of values, handling different row types
                        if hasattr(row, '__iter__') and not isinstance(row, (str, bytes)):
                            # Row is iterable (list, tuple, or pyodbc.Row)
                            row_values = [str(cell) if cell is not None else '' for cell in row]
                        else:
                            # Single value
                            row_values = [str(row) if row is not None else '']
                        writer.writerow(row_values)

            elif file_format.lower() == 'txt':
                with open(filepath, 'w', encoding='utf-8') as txtfile:
                    # Write headers
                    txtfile.write('\t'.join(column_names) + '\n')

                    # Write data rows
                    for row in result:
                        # Convert row to list of values, handling different row types
                        if hasattr(row, '__iter__') and not isinstance(row, (str, bytes)):
                            # Row is iterable (list, tuple, or pyodbc.Row)
                            row_values = [str(cell) if cell is not None else '' for cell in row]
                        else:
                            # Single value
                            row_values = [str(row) if row is not None else '']
                        txtfile.write('\t'.join(row_values) + '\n')

            row_count = len(result)

            # Return a download-ready message
            return (f"Exported {row_count:,} rows to {file_format.upper()} format. "
                    f"File: {filename} "
                    f"Ready for download from server.")

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return f"Export failed: {e}"

    # Enhanced src/plugins/database_plugin.py - Add LIKE search guidance

    # Enhanced src/plugins/database_plugin.py - Add ProdGroupDes and fix product searches

    @kernel_function(
        name="query",
        description=(
                "Query the CRPAF database using SQL Server syntax. "
                "IMPORTANT: Only query these approved production tables: "

                "ACTUAL SALES DATA (INVOICE-BASED): "
                "- pmsalespbi: ACTUAL INVOICE SALES DATA by customer (PRIMARY SALES TABLE). "
                "  Key columns: CaptureDate, Company, CustomerGroup, CustomerName, Product, ProductCategoryID, "
                "  ProdDivID, ProdGroupID, ProdGroupDes, Quantity, Sales, Cost, Margin, InvMonth, InvQuarter, InvWeek, InvYear, InvDate "
                "  Use this table when users ask about 'sales to customers', 'how much did we sell', 'revenue', 'margins', 'product categories' "

                "EBAY MARKET DATA (COMPETITIVE INTELLIGENCE): "
                "- ebayWT: eBay auction listings (LARGE TABLE - 2M+ records). Market pricing data. "
                "  Key columns: OEAN, Price, Quantity, CaptureDate, SellerID, Title, EndTime "
                "- ebayWT_NF: eBay auctions for parts NOT in our inventory (competitive analysis). "
                "  Key columns: OEAN, DeltaSold (sales indicator), SoldPrice, SoldDate "
                "- ebayNF_SupplierMatch: Competitor parts with supplier matching data. "
                "  Key columns: OEAN, SupplierName, SupplierPrice, PartDescription (NOTE: Supplier fields may be NULL) "

                "CRITICAL SEARCH PATTERNS: "
                "- ALWAYS use LIKE with wildcards for customer AND product searches "
                "- Customer names often have variations (e.g., 'Autozone', 'Autozone USA', 'AutoZone Inc') "
                "- Product names/descriptions often have variations (e.g., 'AAE-HPS Racks', 'AAE-HPS Pumps') "
                "- Use pattern: WHERE CustomerName LIKE '%AUTOZONE%' AND Product LIKE '%AAE-HPS%' "
                "- For product category analysis: Use ProdGroupDes LIKE '%RACK%' or '%PUMP%' "
                "- Case insensitive searches: Use UPPER() function for consistency "

                "SEARCH STRATEGY: "
                "1. For customer searches: WHERE UPPER(CustomerName) LIKE '%[CUSTOMER]%' "
                "2. For product searches: WHERE UPPER(Product) LIKE '%[PRODUCT]%' OR UPPER(ProdGroupDes) LIKE '%[CATEGORY]%' "
                "3. For product categories: GROUP BY ProdGroupDes to see category performance "
                "4. If no results, suggest checking spelling or trying broader search terms "

                "PRODUCT CATEGORY ANALYSIS (ProdGroupDes): "
                "- ProdGroupDes shows product categories (e.g., 'AAE-HPS Pumps', 'Oil Filters', 'Brake Parts') "
                "- Use for questions like 'best selling product category', 'pump sales', 'filter performance' "
                "- Query pattern: SELECT ProdGroupDes, SUM(Sales), SUM(Quantity) FROM pmsalespbi GROUP BY ProdGroupDes ORDER BY SUM(Sales) DESC "
                "- For specific categories: WHERE UPPER(ProdGroupDes) LIKE '%PUMP%' OR '%RACK%' OR '%FILTER%' "

                "TABLE USAGE GUIDELINES: "
                "- For customer sales questions → Use pmsalespbi with CustomerName LIKE "
                "- For product/category sales → Use pmsalespbi with Product LIKE or ProdGroupDes LIKE "
                "- For product category analysis → Use pmsalespbi GROUP BY ProdGroupDes "
                "- For market pricing questions → Use ebayWT/ebayWT_NF "
                "- For competitive analysis → Use ebayNF_SupplierMatch "

                "COLUMN DETAILS: "
                "- CustomerName: Individual customer names (use LIKE for searches) "
                "- CustomerGroup: Customer category/grouping "
                "- Product: Specific part/product identifier (use LIKE for searches) "
                "- ProdGroupDes: Product category description - KEY for category analysis "
                "- Sales: Revenue amount "
                "- Quantity: Units sold "
                "- Margin: Profit margin "
                "- InvDate/CaptureDate: Transaction dates "

                "EXAMPLE IMPROVED QUERIES: "
                "- Customer sales: SELECT CustomerName, SUM(Sales), SUM(Quantity) FROM pmsalespbi WHERE UPPER(CustomerName) LIKE '%AUTOZONE%' GROUP BY CustomerName "
                "- Product sales: SELECT Product, ProdGroupDes, SUM(Sales), SUM(Quantity) FROM pmsalespbi WHERE UPPER(Product) LIKE '%AAE-HPS%' GROUP BY Product, ProdGroupDes "
                "- Category performance: SELECT ProdGroupDes, SUM(Sales) as TotalSales, SUM(Quantity) as TotalQty FROM pmsalespbi GROUP BY ProdGroupDes ORDER BY TotalSales DESC "
                "- Best selling racks: SELECT Product, SUM(Sales), SUM(Quantity) FROM pmsalespbi WHERE UPPER(ProdGroupDes) LIKE '%RACK%' GROUP BY Product ORDER BY SUM(Sales) DESC "
                "- Pump sales by customer: SELECT CustomerName, SUM(Sales) FROM pmsalespbi WHERE UPPER(ProdGroupDes) LIKE '%PUMP%' GROUP BY CustomerName ORDER BY SUM(Sales) DESC "
                "- Monthly category trends: SELECT ProdGroupDes, InvMonth, InvYear, SUM(Sales) FROM pmsalespbi WHERE UPPER(ProdGroupDes) LIKE '%FILTER%' GROUP BY ProdGroupDes, InvMonth, InvYear "

                "WHEN USER SEARCHES FOR PRODUCTS: "
                "- First try Product LIKE '%[searchterm]%' "
                "- If no results, try ProdGroupDes LIKE '%[searchterm]%' "
                "- Examples: 'AAE-HPS Racks' → try Product LIKE '%AAE-HPS%' AND ProdGroupDes LIKE '%RACK%' "
                "- 'best selling pumps' → ProdGroupDes LIKE '%PUMP%' GROUP BY Product "

                "FORBIDDEN TABLE PATTERNS: "
                "- Tables ending in '_backup', '_temp', '_staging', '_work' "
                "- Tables starting with 'temp_', 'backup_', 'old_', 'archive_' "
                "- Any table containing 'test', 'dev', 'intermediate' in the name "
                "- Tables not explicitly listed in the approved list above "

                "QUERY BEST PRACTICES: "
                "- For large result sets (>100 rows), use SELECT TOP N to limit results "
                "- Use InvDate for sales data timestamps (pmsalespbi) "
                "- Use CaptureDate for eBay data timestamps "
                "- Use proper SQL Server syntax (SELECT TOP N, not LIMIT N) "
                "- Handle NULL values appropriately "
                "- ALWAYS use LIKE with % wildcards for name/text searches unless user specifies exact match "
                "- Use UPPER() function for case-insensitive searches "
                "- For product searches, try both Product and ProdGroupDes columns "

                "When users ask about sales, revenue, customers, or 'how much did we sell', use pmsalespbi as the primary source with LIKE pattern matching. "
                "When users ask about product categories or 'best selling [category]', use ProdGroupDes for grouping and analysis. "
                "When users ask about market pricing or competitive data, use the eBay tables. "
                "If a search returns no results, automatically suggest and try LIKE pattern searches with partial matches in both Product and ProdGroupDes columns."
        )
    )

    def query(self, query: Annotated[str, "The SQL query"]) -> Annotated[
        Union[List[pyodbc.Row], str], "The rows returned or a message"]:
        logger.info(f"Running database plugin with query: {query}")

        # Validate forbidden patterns
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

        # Check for potentially large queries BEFORE executing
        estimated_rows = self._estimate_row_count(query)

        if estimated_rows > self.max_display_rows:
            return (f"WARNING: This query will return approximately {estimated_rows:,} rows, "
                    f"which is too large to display. Consider:\n"
                    f"1. Adding 'TOP {self.max_display_rows}' to see a sample\n"
                    f"2. Adding WHERE conditions to filter the data\n"
                    f"3. Ask me to 'export the full results to CSV file' if you need all data\n\n"
                    f"Would you like me to show just the first {self.max_display_rows} rows instead?")

        # Execute the query
        result = self.db.query(query)

        # Check actual result size even if estimation failed
        if isinstance(result, list) and len(result) > self.max_display_rows:
            return (f"Query returned {len(result):,} rows (showing first {self.max_display_rows}):\n\n" +
                    str(result[:self.max_display_rows]) +
                    f"\n\n... and {len(result) - self.max_display_rows:,} more rows. "
                    f"Ask me to 'export full results to CSV' if you need all data.")

        print(f">> DB RESULT: {result}")
        return result

    # Add a helper function for the AI to use when searches return no results
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
            # Try to find similar customer names
            customer_query = f"SELECT DISTINCT TOP 10 CustomerName FROM pmsalespbi WHERE UPPER(CustomerName) LIKE '%{search_term.upper()}%' ORDER BY CustomerName"
            customer_result = self.db.query(customer_query)

            # Try to find similar product names
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
            # Get row count
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            result = self.db.query(count_query)

            if isinstance(result, str):
                return f"Error getting table size: {result}"

            if result:
                row_count = result[0][0]
                # In get_table_size method
                logger.info(
                    f"Table '{table_name}' contains {row_count:,} rows. WARNING: Very large - Use specific WHERE conditions or TOP N")

                # Provide context about query performance
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