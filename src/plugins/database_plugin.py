# database_plugin.py
# Integrated version combining comprehensive business intelligence prompt
# with clean code structure and proper 360-degree analysis capabilities

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

# Comprehensive business intelligence prompt with all the detailed guidance
comprehensive_query_description = """
Query the CRPAF database using SQL Server syntax. 
IMPORTANT: Only query these approved production tables:

ACTUAL SALES DATA (INVOICE-BASED):
- pmsalespbi: ACTUAL INVOICE SALES DATA by customer (PRIMARY SALES TABLE).
  Key columns: CaptureDate, Company, CustomerGroup, CustomerName, Product, ProductCategoryID,
  ProdDivID, ProdGroupID, ProdGroupDes, Quantity, Sales, Cost, Margin, InvMonth, InvQuarter, InvWeek, InvYear, InvDate
  Use this table when users ask about 'sales to customers', 'how much did we sell', 'revenue', 'margins', 'product categories'

PRODUCT PERFORMANCE & INVENTORY ANALYTICS:
- rightScore_results: PRODUCT SCORING & INVENTORY OPTIMIZATION DATA (ANALYTICAL TABLE).
  Key columns: CaptureDate, LastUpdated, Product, ProdGroupDes, Flag3Year, Flag1Year,
  ForecastScore, VIOScore, CompScore, eBayScore, MSRPScore, DistScore, ProfitScore, StockScore, OverallScore
  Use for inventory optimization, product performance analysis, dead stock identification
  SCORING SYSTEM: Higher scores = better performance (5 = excellent, 0 = poor)
  Flag3Year: 1 = product introduced within last 3 years, 0 = older product
  Flag1Year: 1 = product introduced within last year, 0 = older than one year
  StockScore: Focuses on inventory movement and stocking decisions
  OverallScore: Comprehensive product performance across all metrics
  Use this table for questions about 'product performance', 'inventory optimization', 'dead stock', 'product scoring'

EBAY MARKET DATA (COMPETITIVE INTELLIGENCE):
- ebayWT: eBay auction listings (LARGE TABLE - 2M+ records). Market pricing data.
  Key columns: OEAN, UnitPrice (nvarchar - convert to numeric for calculations), Quantity, CaptureDate, SellerID, Title, EndTime
  IMPORTANT: UnitPrice is stored as nvarchar(100) - use TRY_CONVERT(decimal(10,2), UnitPrice) for numeric operations
- ebayWT_NF: eBay auctions for parts NOT in our inventory (competitive analysis).
  Key columns: OEAN, DeltaSold (sales indicator), SoldPrice, SoldDate
- ebayNF_SupplierMatch: Competitor parts with supplier matching data.
  Key columns: OEAN, SupplierName, SupplierPrice, PartDescription (NOTE: Supplier fields may be NULL)

PRICING DATA (OE MSRP & SUPERSESSIONS):
- OEPriceBookPBI: OE MANUFACTURER PRICING DATA from Standard Motor Products (monthly updates).
  Key columns: BatchID, Make, [Part Number] (OEAN), [Part Description], [Dealer List Price],
  [Date Last Price Change], [Supperseded Flag], [Superseded Part Number], [Country ID], Notes, Status
  Use for MSRP/list price queries, supersession checks, part pricing analysis
  NOTE: Column names have spaces and brackets - use [Part Number] not Part_Number
  MSRP queries: SELECT [Part Number], [Dealer List Price] FROM OEPriceBookPBI WHERE [Part Number] = 'PFF5225R'
  Supersession queries: SELECT [Part Number], [Supperseded Flag], [Superseded Part Number] FROM OEPriceBookPBI WHERE [Part Number] = 'PFF5225R'
  Price history: SELECT [Part Number], [Dealer List Price], [Date Last Price Change] FROM OEPriceBookPBI WHERE [Part Number] LIKE '%PFF%'

INTERNET COMPETITION DATA (WEB SCRAPED COMPETITORS):
- InternetCompData: COMPETITOR PRICING & AVAILABILITY from web scraping (competitive intelligence).
  Key columns: [File_Name], [Record_ID], [OEAN], [Competitor Name], [Description], [Price], [Availability], [Addtl OE Numbers], [Competitor Part Number]
  Use for competitive pricing analysis, market presence checks, availability comparisons
  NOTE: Column names have spaces and brackets - use [Competitor Name] not Competitor_Name
  Competition queries: SELECT [OEAN], [Competitor Name], [Price], [Availability] FROM InternetCompData WHERE [OEAN] = 'PFF5225R'
  Price comparison: SELECT [OEAN], AVG([Price]) as AvgCompetitorPrice, COUNT(*) as CompetitorCount FROM InternetCompData WHERE [OEAN] = 'PFF5225R' GROUP BY [OEAN]
  Competitor analysis: SELECT [Competitor Name], COUNT(*) as PartCount, AVG([Price]) as AvgPrice FROM InternetCompData GROUP BY [Competitor Name] ORDER BY PartCount DESC

SUPPLIER SOURCING DATA (INTERNAL SUPPLIER CATALOGS):
- Suppliers: SUPPLIER SOURCING OPTIONS from MongoDB-processed Excel catalogs (200+ supplier files).
  Key columns: [OEAN], [Name], [collection]
  Use for supplier sourcing, availability checks, procurement options
  collection field: Concatenation of file path + Excel sheet name for supplier traceability
  Sourcing queries: SELECT [OEAN], [Name], [collection] FROM Suppliers WHERE [OEAN] = 'PFF5225R'
  Supplier coverage: SELECT [collection], COUNT(*) as PartCount FROM Suppliers GROUP BY [collection] ORDER BY PartCount DESC
  Multi-source parts: SELECT [OEAN], COUNT(*) as SupplierCount FROM Suppliers GROUP BY [OEAN] HAVING COUNT(*) > 1 ORDER BY SupplierCount DESC

PRODUCT-TO-OEAN MAPPING (ROSETTA STONE):
- rightStock_ProductOEs: PRODUCT-TO-OEAN CROSS-REFERENCE (enables product-level intelligence).
  Key columns: [CaptureDate], [Product], [OE]
  Use to map internal products to OEANs for comprehensive market analysis
  Product mapping: SELECT [Product], [OE] FROM rightStock_ProductOEs WHERE [Product] = 'HP1000'
  OEAN lookup: SELECT [Product] FROM rightStock_ProductOEs WHERE [OE] = 'PFF5225R'
  Product OEAN count: SELECT [Product], COUNT([OE]) as OEANCount FROM rightStock_ProductOEs GROUP BY [Product] ORDER BY OEANCount DESC

360° OEAN INTELLIGENCE QUERIES (COMPREHENSIVE PART ANALYSIS):
When users ask about a specific OEAN, provide comprehensive intelligence across all tables:
CRITICAL: Always check rightStock_ProductOEs to find corresponding internal product codes for sales/performance data
CRITICAL: Use proper table aliases and exact column names with brackets where required
- Product mapping: SELECT p.[Product] FROM rightStock_ProductOEs p WHERE p.[OE] = '17127531579'
- MSRP from OEPriceBookPBI: SELECT o.[Part Number], o.[Dealer List Price], o.[Supperseded Flag] FROM OEPriceBookPBI o WHERE o.[Part Number] = '17127531579'
- Competition from InternetCompData: SELECT i.[Competitor Name], i.[Price], i.[Availability] FROM InternetCompData i WHERE i.[OEAN] = '17127531579'
- Supplier options from Suppliers: SELECT s.[Name], s.[collection] FROM Suppliers s WHERE s.[OEAN] = '17127531579'
- eBay activity from ebayWT: SELECT COUNT(*) as ListingCount, AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) as AvgEbayPrice FROM ebayWT e WHERE e.OEAN = '17127531579' AND TRY_CONVERT(decimal(10,2), e.UnitPrice) IS NOT NULL
- Our sales performance: SELECT p.[Product], SUM(s.Sales) as TotalSales, SUM(s.Quantity) as TotalQty FROM rightStock_ProductOEs p JOIN pmsalespbi s ON p.[Product] = s.Product WHERE p.[OE] = '17127531579' GROUP BY p.[Product]
- Performance scoring: SELECT p.[Product], r.OverallScore, r.StockScore, r.CompScore FROM rightStock_ProductOEs p JOIN rightScore_results r ON p.[Product] = r.Product WHERE p.[OE] = '17127531579'

360° PRODUCT INTELLIGENCE QUERIES (COMPREHENSIVE PRODUCT ANALYSIS):
When users ask about internal products, use rightStock_ProductOEs to map to OEANs then analyze across all tables:
CRITICAL: Use proper table aliases and exact column names with brackets where required
- Product OEAN mapping: SELECT p.[Product], p.[OE] FROM rightStock_ProductOEs p WHERE p.[Product] = 'CHR0406R'
- MSRP for product OEANs: SELECT p.[Product], p.[OE], o.[Dealer List Price] FROM rightStock_ProductOEs p LEFT JOIN OEPriceBookPBI o ON p.[OE] = o.[Part Number] WHERE p.[Product] = 'CHR0406R'
- Competition for product OEANs: SELECT p.[Product], p.[OE], i.[Competitor Name], i.[Price] FROM rightStock_ProductOEs p LEFT JOIN InternetCompData i ON p.[OE] = i.[OEAN] WHERE p.[Product] = 'CHR0406R'
- Suppliers for product OEANs: SELECT p.[Product], p.[OE], s.[Name], s.[collection] FROM rightStock_ProductOEs p LEFT JOIN Suppliers s ON p.[OE] = s.[OEAN] WHERE p.[Product] = 'CHR0406R'
- eBay activity for product OEANs: SELECT p.[Product], p.[OE], COUNT(e.OEAN) as ListingCount, AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) as AvgPrice FROM rightStock_ProductOEs p LEFT JOIN ebayWT e ON p.[OE] = e.OEAN WHERE p.[Product] = 'CHR0406R' GROUP BY p.[Product], p.[OE]
- Product sales performance: SELECT s.Product, SUM(s.Sales) as TotalSales, SUM(s.Quantity) as TotalQty FROM pmsalespbi s WHERE s.Product = 'CHR0406R' GROUP BY s.Product
- Product performance scores: SELECT r.Product, r.OverallScore, r.StockScore, r.CompScore FROM rightScore_results r WHERE r.Product = 'CHR0406R'

COMPETITIVE INTELLIGENCE QUERIES:
- Market coverage: SELECT i.[OEAN], o.[Dealer List Price] as MSRP, AVG(i.[Price]) as AvgCompPrice, COUNT(i.[Competitor Name]) as CompetitorCount FROM InternetCompData i LEFT JOIN OEPriceBookPBI o ON i.[OEAN] = o.[Part Number] GROUP BY i.[OEAN], o.[Dealer List Price]
- Pricing gaps: SELECT i.[OEAN], o.[Dealer List Price] as MSRP, MIN(i.[Price]) as LowestCompPrice, o.[Dealer List Price] - MIN(i.[Price]) as PricingGap FROM InternetCompData i JOIN OEPriceBookPBI o ON i.[OEAN] = o.[Part Number] GROUP BY i.[OEAN], o.[Dealer List Price] ORDER BY PricingGap DESC
- Competitor part coverage: SELECT [Competitor Name], COUNT(DISTINCT [OEAN]) as UniquePartsOffered FROM InternetCompData GROUP BY [Competitor Name] ORDER BY UniquePartsOffered DESC
- High-competition parts: SELECT [OEAN], COUNT([Competitor Name]) as CompetitorCount FROM InternetCompData GROUP BY [OEAN] HAVING COUNT([Competitor Name]) >= 5 ORDER BY CompetitorCount DESC

SOURCING & PROCUREMENT QUERIES:
- Multi-sourced parts: SELECT [OEAN], COUNT([collection]) as SupplierCount FROM Suppliers GROUP BY [OEAN] HAVING COUNT([collection]) > 1 ORDER BY SupplierCount DESC
- Supplier catalog coverage: SELECT [collection], COUNT([OEAN]) as PartCount FROM Suppliers GROUP BY [collection] ORDER BY PartCount DESC
- Parts with both suppliers and competition: SELECT s.[OEAN], COUNT(DISTINCT s.[collection]) as SupplierCount, COUNT(DISTINCT i.[Competitor Name]) as CompetitorCount FROM Suppliers s JOIN InternetCompData i ON s.[OEAN] = i.[OEAN] GROUP BY s.[OEAN] ORDER BY CompetitorCount DESC

CRITICAL SEARCH PATTERNS:
- ALWAYS use LIKE with wildcards for customer AND product searches
- Customer names often have variations (e.g., 'Autozone', 'Autozone USA', 'AutoZone Inc')
- Product names/descriptions often have variations (e.g., 'AAE-HPS Racks', 'AAE-HPS Pumps')
- Use pattern: WHERE CustomerName LIKE '%AUTOZONE%' AND Product LIKE '%AAE-HPS%'
- For product category analysis: Use ProdGroupDes LIKE '%RACK%' or '%PUMP%'
- Case insensitive searches: Use UPPER() function for consistency
- For OEAN searches across tables: Use exact match first, then LIKE patterns if needed

SEARCH STRATEGY:
1. For customer searches: WHERE UPPER(CustomerName) LIKE '%[CUSTOMER]%'
2. For product searches: WHERE UPPER(Product) LIKE '%[PRODUCT]%' OR UPPER(ProdGroupDes) LIKE '%[CATEGORY]%'
3. For product categories: GROUP BY ProdGroupDes to see category performance
4. For inventory/performance analysis: Use rightScore_results with appropriate score filters
5. For MSRP/pricing questions: Use OEPriceBookPBI with [Part Number] searches
6. For competitive intelligence: Use InternetCompData for competitor pricing
7. For sourcing options: Use Suppliers for internal procurement possibilities
8. For comprehensive OEAN analysis: Query multiple tables and present unified intelligence
9. If no results, suggest checking spelling or trying broader search terms

TABLE USAGE GUIDELINES:
- For customer sales questions → Use pmsalespbi with CustomerName LIKE
- For product/category sales → Use pmsalespbi with Product LIKE or ProdGroupDes LIKE
- For product performance analysis → Use rightScore_results with score filters
- For inventory optimization → Use rightScore_results focusing on StockScore and OverallScore
- For dead stock identification → Use rightScore_results WHERE StockScore <= 2 AND Flag3Year = 0
- For new product tracking → Use rightScore_results WHERE Flag1Year = 1 or Flag3Year = 1
- For market pricing questions → Use ebayWT/ebayWT_NF
- For competitive analysis → Use ebayNF_SupplierMatch
- For MSRP/list price questions → Use OEPriceBookPBI with [Part Number] searches
- For supersession checks → Use OEPriceBookPBI [Supperseded Flag] and [Superseded Part Number]
- For competitor pricing → Use InternetCompData with [OEAN] searches
- For sourcing options → Use Suppliers with [OEAN] searches
- For comprehensive part intelligence → Query across multiple tables for complete picture
- For product-to-OEAN mapping → Use rightStock_ProductOEs to connect internal products to market intelligence
- For multi-OEAN product analysis → Use rightStock_ProductOEs to analyze all OEANs for a single product

CRITICAL OEAN/PRODUCT FIELD MAPPING:
Each table uses different field names for part identification - USE THE EXACT FIELD NAME FOR EACH TABLE INCLUDING BRACKETS:
- rightStock_ProductOEs: [OE] (maps internal products to OEANs - MUST USE BRACKETS)
- OEPriceBookPBI: [Part Number] (OEAN field with brackets)
- InternetCompData: [OEAN], [Price] (ALL fields need brackets)
- Suppliers: [OEAN] (OEAN field with brackets)
- ebayWT: OEAN, UnitPrice (nvarchar - use TRY_CONVERT for calculations)
- ebayWT_NF: OEAN (field without brackets)
- ebayNF_SupplierMatch: OEAN (field without brackets)
- pmsalespbi: Product (internal product code, no brackets)
- rightScore_results: Product (internal product code, no brackets)

CRITICAL JOIN PATTERNS WITH PROPER ALIASES:
- To get OEANs for a product: SELECT p.[Product], p.[OE] FROM rightStock_ProductOEs p WHERE p.[Product] = 'CHR0406R'
- To get product for an OEAN: SELECT p.[Product] FROM rightStock_ProductOEs p WHERE p.[OE] = '17127531579'
- MSRP by OEAN: SELECT o.[Part Number], o.[Dealer List Price] FROM OEPriceBookPBI o WHERE o.[Part Number] = '17127531579'
- Competition by OEAN: SELECT i.[Competitor Name], i.[Price], i.[Availability] FROM InternetCompData i WHERE i.[OEAN] = '17127531579'
- Suppliers by OEAN: SELECT s.[Name], s.[collection] FROM Suppliers s WHERE s.[OEAN] = '17127531579'
- eBay by OEAN: SELECT COUNT(*) as Listings, AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) as AvgPrice FROM ebayWT e WHERE e.OEAN = '17127531579' AND TRY_CONVERT(decimal(10,2), e.UnitPrice) IS NOT NULL
- Sales by product: SELECT s.Product, SUM(s.Sales) as Revenue FROM pmsalespbi s WHERE s.Product = 'CHR0406R'
- Scoring by product: SELECT r.Product, r.OverallScore FROM rightScore_results r WHERE r.Product = 'CHR0406R'

CRITICAL DATA TYPE HANDLING:
- ebayWT.UnitPrice is stored as nvarchar(100) - ALWAYS use TRY_CONVERT(decimal(10,2), UnitPrice) for numeric operations
- Add WHERE TRY_CONVERT(decimal(10,2), UnitPrice) IS NOT NULL to filter out non-numeric values
- For eBay price queries, always convert text to decimal before AVG, MIN, MAX operations
- Example: AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) instead of AVG(e.UnitPrice)

EXAMPLE COMPREHENSIVE OEAN QUERIES:
Complete OEAN Intelligence (when user asks about a specific OEAN like '17127531579'):
1. Product mapping: SELECT [Product] FROM rightStock_ProductOEs WHERE [OE] = '17127531579'
2. MSRP: SELECT [Part Number], [Dealer List Price], [Supperseded Flag] FROM OEPriceBookPBI WHERE [Part Number] = '17127531579'
3. Competition: SELECT [Competitor Name], [Price], [Availability] FROM InternetCompData WHERE [OEAN] = '17127531579' ORDER BY [Price]
4. Suppliers: SELECT [Name], [collection] FROM Suppliers WHERE [OEAN] = '17127531579'
5. eBay Market: SELECT COUNT(*) as Listings, AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) as AvgPrice FROM ebayWT e WHERE e.OEAN = '17127531579' AND TRY_CONVERT(decimal(10,2), e.UnitPrice) IS NOT NULL
6. Our Performance (via product mapping): SELECT p.[Product], SUM(s.Sales) as Revenue, SUM(s.Quantity) as UnitsSold FROM rightStock_ProductOEs p JOIN pmsalespbi s ON p.[Product] = s.Product WHERE p.[OE] = '17127531579' GROUP BY p.[Product]
7. Performance Score (via product mapping): SELECT p.[Product], r.OverallScore, r.StockScore FROM rightStock_ProductOEs p JOIN rightScore_results r ON p.[Product] = r.Product WHERE p.[OE] = '17127531579'

EXAMPLE COMPREHENSIVE PRODUCT QUERIES:
Complete Product Intelligence (when user asks about a product like 'CHR0406R'):
1. Product OEANs: SELECT [Product], [OE] FROM rightStock_ProductOEs WHERE [Product] = 'CHR0406R'
2. Sales Performance: SELECT Product, SUM(Sales) as TotalSales, SUM(Quantity) as TotalQty FROM pmsalespbi WHERE Product = 'CHR0406R' GROUP BY Product
3. Performance Scores: SELECT Product, OverallScore, StockScore, CompScore FROM rightScore_results WHERE Product = 'CHR0406R'
4. MSRP for all OEANs: SELECT p.[OE], o.[Dealer List Price] FROM rightStock_ProductOEs p JOIN OEPriceBookPBI o ON p.[OE] = o.[Part Number] WHERE p.[Product] = 'CHR0406R'
5. Competition for all OEANs: SELECT p.[OE], i.[Competitor Name], i.[Price] FROM rightStock_ProductOEs p JOIN InternetCompData i ON p.[OE] = i.[OEAN] WHERE p.[Product] = 'CHR0406R' ORDER BY i.[Price]
6. Suppliers for all OEANs: SELECT p.[OE], s.[Name] FROM rightStock_ProductOEs p JOIN Suppliers s ON p.[OE] = s.[OEAN] WHERE p.[Product] = 'CHR0406R'
7. eBay activity for all OEANs: SELECT p.[OE], COUNT(e.OEAN) as Listings FROM rightStock_ProductOEs p LEFT JOIN ebayWT e ON p.[OE] = e.OEAN WHERE p.[Product] = 'CHR0406R' GROUP BY p.[OE]

MARKET INTELLIGENCE QUERIES:
- Price comparison across sources: SELECT 'MSRP' as Source, o.[Dealer List Price] as Price FROM OEPriceBookPBI o WHERE o.[Part Number] = 'PFF5225R' UNION ALL SELECT 'Competition', AVG(i.[Price]) FROM InternetCompData i WHERE i.[OEAN] = 'PFF5225R' UNION ALL SELECT 'eBay', AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) FROM ebayWT e WHERE e.OEAN = 'PFF5225R' AND TRY_CONVERT(decimal(10,2), e.UnitPrice) IS NOT NULL
- Competition intensity: SELECT [OEAN], COUNT([Competitor Name]) as CompetitorCount, MIN([Price]) as LowestPrice, MAX([Price]) as HighestPrice FROM InternetCompData GROUP BY [OEAN] ORDER BY CompetitorCount DESC
- Sourcing vs Competition: SELECT s.[OEAN], COUNT(DISTINCT s.[collection]) as SupplierOptions, COUNT(DISTINCT i.[Competitor Name]) as Competitors FROM Suppliers s FULL OUTER JOIN InternetCompData i ON s.[OEAN] = i.[OEAN] GROUP BY s.[OEAN]

FORBIDDEN TABLE PATTERNS:
- Tables ending in '_backup', '_temp', '_staging', '_work'
- Tables starting with 'temp_', 'backup_', 'old_', 'archive_'
- Any table containing 'test', 'dev', 'intermediate' in the name
- Tables not explicitly listed in the approved list above

QUERY BEST PRACTICES:
- For large result sets (>100 rows), use SELECT TOP N to limit results
- Use InvDate for sales data timestamps (pmsalespbi)
- Use CaptureDate/LastUpdated for performance data timestamps (rightScore_results)
- Use [Date Last Price Change] for pricing data timestamps (OEPriceBookPBI)
- Use CaptureDate for eBay data timestamps
- Use proper SQL Server syntax (SELECT TOP N, not LIMIT N)
- Handle NULL values appropriately
- ALWAYS use LIKE with % wildcards for name/text searches unless user specifies exact match
- Use UPPER() function for case-insensitive searches
- For product searches, try both Product and ProdGroupDes columns
- When joining tables, use OEAN/Product/[Part Number] as common keys
- For comprehensive OEAN analysis, suggest follow-up queries across related tables

When users ask about a specific OEAN or part number, ALWAYS first check rightStock_ProductOEs to find corresponding internal product codes, then provide comprehensive intelligence by querying multiple relevant tables including the mapped product data to give a complete market picture including MSRP, competition, sourcing options, eBay activity, our sales performance (via product mapping), and scoring data (via product mapping).
When users ask about sales, revenue, customers, or 'how much did we sell', use pmsalespbi as the primary source with LIKE pattern matching.
When users ask about product performance, inventory optimization, dead stock, or product scoring, use rightScore_results.
When users ask about MSRP, list price, dealer price, supersessions, or manufacturer pricing, use OEPriceBookPBI.
When users ask about competitor pricing, market presence, or 'who else sells this', use InternetCompData.
When users ask about supplier options, sourcing, or 'where can we get this', use Suppliers.
When users ask about market pricing or eBay activity, use the eBay tables.
For any specific OEAN inquiry, automatically suggest related queries across all relevant tables to provide complete market intelligence.
"""


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
        description=comprehensive_query_description
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
