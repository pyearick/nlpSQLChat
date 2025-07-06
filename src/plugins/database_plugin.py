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

    @kernel_function(
        name="query",
        description=(
                "Query the CRPAF database using SQL Server syntax. "
                "IMPORTANT: Only query these approved production tables: "
                "- ebayWT: Contains all eBay records pulled from the eBay API with complete auction data (LARGE TABLE - 2M+ records) "
                "- ebayWT_NF: Contains eBay auctions that are selling (DeltaSold field shows sales) for OEANs we do not carry in our inventory "
                "- ebayNF_SupplierMatch: Contains eBay auctions for parts we don't carry, with additional supplier, pricing, and parts data when available. NOTE: Supplier/pricing fields may be NULL when no matching data exists "
                "DO NOT query any tables with these patterns: "
                "- Tables ending in '_backup', '_temp', '_staging', '_work' "
                "- Tables starting with 'temp_', 'backup_', 'old_', 'archive_' "
                "- Any table containing 'test', 'dev', 'intermediate' in the name "
                "LARGE RESULT HANDLING: "
                "- For queries that might return many rows (>100), always suggest using TOP N to limit results "
                "- If user asks for 'all records' from large tables, offer to export to file instead "
                "- Use SELECT TOP 10 or TOP 100 for initial data exploration "
                "Use SELECT TOP N instead of LIMIT N for row limiting. "
                "Use CONVERT or CAST for date formats. "
                "When identifying newest records, assume 'CaptureDate' column unless told otherwise. "
                "Handle NULL values appropriately when querying supplier/pricing data in ebayNF_SupplierMatch. "
                "Always use proper SQL Server syntax and reference only the approved production tables listed above."
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

    @kernel_function(
        name="export_query_to_csv",
        description=(
                "Export query results to a CSV file when the dataset is too large to display. "
                "Use this when users ask for 'all records' or when a query returns more than 100 rows. "
                "The file will be saved to the server's export directory."
        )
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