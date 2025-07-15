import pyodbc
import re
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TableInfo:
    name: str
    purpose: str
    key_fields: List[str]
    join_fields: List[str]
    size_estimate: str
    update_frequency: str
    notes: str = ""


@dataclass
class Relationship:
    source_table: str
    target_table: str
    join_condition: str
    relationship_type: str  # 'strong', 'medium', 'weak'
    notes: str = ""


class SchemaAnalyzer:
    """Analyze and maintain the database schema documentation"""

    def __init__(self, connection_string: str = None):
        # Try to build connection string from environment if not provided
        if not connection_string:
            connection_string = self._build_connection_string()

        self.connection_string = connection_string
        self.tables: Dict[str, TableInfo] = {}
        self.relationships: List[Relationship] = []
        self.load_current_schema()

    def _build_connection_string(self) -> Optional[str]:
        """Build connection string from environment variables"""
        try:
            server_name = os.getenv('SQL_SERVER_NAME', 'BI-SQL001')
            database_name = os.getenv('SQL_DATABASE_NAME', 'CRPAF')

            # Try username/password first, then fall back to trusted connection
            username = os.getenv('DB_USERNAME')
            password = os.getenv('DB_PASSWORD')

            if username and password:
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={server_name};"
                    f"DATABASE={database_name};"
                    f"UID={username};"
                    f"PWD={password};"
                    "Trusted_Connection=no;"
                    "Connection Timeout=30;"
                )
                logger.info(f"Using SQL authentication for {username}@{server_name}")
            else:
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={server_name};"
                    f"DATABASE={database_name};"
                    "Trusted_Connection=yes;"
                    "Connection Timeout=30;"
                )
                logger.info(f"Using Windows authentication for {server_name}")

            return conn_str

        except Exception as e:
            logger.error(f"Error building connection string: {e}")
            return None

    def load_current_schema(self):
        """Load the current schema from database_plugin.py"""
        # This represents what's currently documented in database_plugin.py
        self.tables = {
            'PMSalesPBI': TableInfo(
                name='PMSalesPBI',
                purpose='ACTUAL INVOICE SALES DATA',
                key_fields=['CustomerName', 'Product', 'InvDate', 'Sales', 'Quantity'],
                join_fields=['Product'],
                size_estimate='Large',
                update_frequency='Daily'
            ),
            'rightScore_results': TableInfo(
                name='rightScore_results',
                purpose='PRODUCT SCORING & OPTIMIZATION',
                key_fields=['Product', 'OverallScore', 'StockScore', 'CompScore'],
                join_fields=['Product'],
                size_estimate='Medium',
                update_frequency='Daily'
            ),
            'rightInventory': TableInfo(
                name='rightInventory',
                purpose='CURRENT INVENTORY LEVELS',
                key_fields=['Product', 'Site', 'Qty', 'Value', 'Status'],
                join_fields=['Product'],
                size_estimate='Medium',
                update_frequency='Daily (5 AM)'
            ),
            'rightStock_ProductOEs': TableInfo(
                name='rightStock_ProductOEs',
                purpose='PRODUCT-TO-OEAN MAPPING',
                key_fields=['Product', 'OE'],
                join_fields=['Product', 'OE'],
                size_estimate='Medium',
                update_frequency='Weekly'
            ),
            'OEPriceBookPBI': TableInfo(
                name='OEPriceBookPBI',
                purpose='OE MANUFACTURER PRICING',
                key_fields=['Part Number', 'Dealer List Price', 'Supperseded Flag'],
                join_fields=['Part Number'],
                size_estimate='Large',
                update_frequency='Monthly'
            ),
            'InternetCompData': TableInfo(
                name='InternetCompData',
                purpose='COMPETITOR PRICING & AVAILABILITY',
                key_fields=['OEAN', 'Competitor Name', 'Price', 'Availability'],
                join_fields=['OEAN'],
                size_estimate='Very Large',
                update_frequency='Daily'
            ),
            'Suppliers': TableInfo(
                name='Suppliers',
                purpose='SUPPLIER SOURCING OPTIONS',
                key_fields=['OEAN', 'Name', 'collection'],
                join_fields=['OEAN'],
                size_estimate='Large',
                update_frequency='Weekly'
            ),
            'ebayWT': TableInfo(
                name='ebayWT',
                purpose='EBAY MARKET PRICING',
                key_fields=['OEAN', 'UnitPrice', 'Quantity', 'CaptureDate'],
                join_fields=['OEAN'],
                size_estimate='Very Large (2M+ records)',
                update_frequency='Daily'
            ),
            'ebayWT_NF': TableInfo(
                name='ebayWT_NF',
                purpose='EBAY PARTS NOT IN INVENTORY',
                key_fields=['OEAN', 'DeltaSold', 'SoldPrice'],
                join_fields=['OEAN'],
                size_estimate='Large',
                update_frequency='Daily'
            ),
            'eBayNF_SupplierMatch': TableInfo(
                name='eBayNF_SupplierMatch',
                purpose='COMPETITOR PARTS WITH SUPPLIER MATCHING',
                key_fields=['OEAN', 'SupplierName', 'SupplierPrice'],
                join_fields=['OEAN'],
                size_estimate='Medium',
                update_frequency='Weekly'
            )
        }

        # Define known relationships
        self.relationships = [
            Relationship('PMSalesPBI', 'rightScore_results', 'Product', 'strong'),
            Relationship('PMSalesPBI', 'rightInventory', 'Product', 'strong'),
            Relationship('PMSalesPBI', 'rightStock_ProductOEs', 'Product', 'strong'),
            Relationship('rightScore_results', 'rightInventory', 'Product', 'strong'),
            Relationship('rightStock_ProductOEs', 'OEPriceBookPBI', 'OE -> Part Number', 'strong'),
            Relationship('rightStock_ProductOEs', 'InternetCompData', 'OE -> OEAN', 'strong'),
            Relationship('rightStock_ProductOEs', 'Suppliers', 'OE -> OEAN', 'strong'),
            Relationship('rightStock_ProductOEs', 'ebayWT', 'OE -> OEAN', 'strong'),
            Relationship('OEPriceBookPBI', 'InternetCompData', 'Part Number -> OEAN', 'medium'),
            Relationship('OEPriceBookPBI', 'Suppliers', 'Part Number -> OEAN', 'medium'),
            Relationship('InternetCompData', 'Suppliers', 'OEAN', 'weak'),
            Relationship('InternetCompData', 'ebayWT', 'OEAN', 'weak')
        ]

    def test_connection(self) -> bool:
        """Test the database connection"""
        if not self.connection_string:
            logger.error("No connection string available")
            return False

        try:
            logger.info("Testing database connection...")
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()

            # Simple test query
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()

            # Get database info
            cursor.execute("SELECT DB_NAME() as database_name, @@SERVERNAME as server_name")
            db_info = cursor.fetchone()

            conn.close()

            if result and result[0] == 1:
                logger.info(f"✅ Connection successful to {db_info[1]}/{db_info[0]}")
                return True
            else:
                logger.error("❌ Connection test failed")
                return False

        except pyodbc.Error as e:
            logger.error(f"❌ Database connection failed: {e}")
            logger.info("Check server name, database name, and credentials in .env file")
            return False
        except Exception as e:
            logger.error(f"❌ Connection test error: {e}")
            return False

    def discover_actual_schema(self) -> Dict[str, List[str]]:
        """Discover actual database schema"""
        if not self.connection_string:
            logger.warning("No connection string available, cannot discover actual schema")
            return {}

        try:
            logger.info("Connecting to database to discover schema...")
            conn = pyodbc.connect(self.connection_string)
            cursor = conn.cursor()

            # Get list of tables (exclude system tables)
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                    AND TABLE_SCHEMA = 'dbo'
                    AND TABLE_NAME NOT LIKE 'sys%'
                    AND TABLE_NAME NOT LIKE 'msreplication%'
                ORDER BY TABLE_NAME
            """)

            actual_tables = {}
            table_rows = cursor.fetchall()
            logger.info(f"Found {len(table_rows)} tables in database")

            for row in table_rows:
                table_name = row[0]

                # Get columns for each table
                cursor.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = ? AND TABLE_SCHEMA = 'dbo'
                    ORDER BY ORDINAL_POSITION
                """, table_name)

                columns = [(col[0], col[1], col[2], col[3]) for col in cursor.fetchall()]
                actual_tables[table_name] = columns

                if table_name in self.tables:
                    logger.debug(f"✓ Found documented table: {table_name}")
                else:
                    logger.debug(f"? Found undocumented table: {table_name}")

            conn.close()
            logger.info("Schema discovery completed successfully")
            return actual_tables

        except pyodbc.Error as e:
            logger.error(f"Database connection error: {e}")
            logger.info("Make sure SQL Server is accessible and credentials are correct")
            return {}
        except Exception as e:
            logger.error(f"Error discovering schema: {e}")
            return {}

    def validate_documented_tables(self, actual_schema: Dict[str, List[str]]) -> List[str]:
        """Validate that documented tables exist in actual database"""
        issues = []

        # Create case-insensitive lookup for actual tables
        actual_tables_lower = {table.lower(): table for table in actual_schema.keys()}

        for table_name in self.tables.keys():
            table_name_lower = table_name.lower()

            if table_name_lower not in actual_tables_lower:
                issues.append(f"❌ Documented table '{table_name}' not found in actual database")
            else:
                # Get the actual table name (correct case)
                actual_table_name = actual_tables_lower[table_name_lower]

                # Check if key fields exist (case-insensitive)
                actual_columns = [col[0] for col in actual_schema[actual_table_name]]
                actual_columns_lower = [col.lower() for col in actual_columns]
                table_info = self.tables[table_name]

                for field in table_info.key_fields:
                    # Handle bracketed field names
                    clean_field = field.replace('[', '').replace(']', '').lower()
                    field_lower = field.lower()

                    if clean_field not in actual_columns_lower and field_lower not in actual_columns_lower:
                        issues.append(
                            f"⚠️ Key field '{field}' not found in table '{table_name}' (actual: {actual_table_name})")
                        logger.debug(
                            f"Available columns in {actual_table_name}: {actual_columns[:10]}...")  # Show first 10 columns

                logger.debug(f"✓ Validated table {table_name} -> {actual_table_name}: {len(actual_columns)} columns")

        return issues

    def find_undocumented_tables(self, actual_schema: Dict[str, List[str]]) -> List[str]:
        """Find tables that exist but aren't documented"""
        documented_tables_lower = {table.lower() for table in self.tables.keys()}
        actual_tables = set(actual_schema.keys())

        # Filter out system tables and obvious test/temp tables
        excluded_patterns = [
            r'.*_backup$', r'.*_temp$', r'.*_staging$', r'.*_work$',
            r'^temp_.*', r'^backup_.*', r'^old_.*', r'^archive_.*',
            r'.*test.*', r'.*dev.*', r'.*intermediate.*',
            r'^sys.*', r'^msreplication.*', r'^queue.*'
        ]

        undocumented = []
        for table in actual_tables:
            # Check case-insensitive if it's documented
            if table.lower() not in documented_tables_lower:
                # Check if it matches exclusion patterns
                if not any(re.match(pattern, table, re.IGNORECASE) for pattern in excluded_patterns):
                    undocumented.append(table)

        return sorted(undocumented)  # Sort for consistent output

    def analyze_relationship_gaps(self) -> List[str]:
        """Analyze potential missing relationships"""
        gaps = []

        # Find tables with similar join fields that aren't connected
        join_field_map = {}
        for table_name, table_info in self.tables.items():
            for field in table_info.join_fields:
                if field not in join_field_map:
                    join_field_map[field] = []
                join_field_map[field].append(table_name)

        # Look for potential connections
        for field, tables in join_field_map.items():
            if len(tables) > 1:
                # Check if all combinations are documented
                for i, table1 in enumerate(tables):
                    for table2 in tables[i + 1:]:
                        # Check if this relationship exists
                        relationship_exists = any(
                            (r.source_table == table1 and r.target_table == table2) or
                            (r.source_table == table2 and r.target_table == table1)
                            for r in self.relationships
                        )

                        if not relationship_exists:
                            gaps.append(f"Potential missing relationship: {table1} ↔ {table2} via {field}")

        return gaps

    def generate_maintenance_report(self) -> str:
        """Generate a comprehensive maintenance report"""
        report = []
        report.append("=" * 80)
        report.append("VOICE SQL SCHEMA MAINTENANCE REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Connection test
        report.append("🔌 DATABASE CONNECTION")
        report.append("-" * 40)
        if self.connection_string:
            if self.test_connection():
                report.append("✅ Database connection successful")
            else:
                report.append("❌ Database connection failed")
                report.append("⚠️ Schema validation will be skipped")
                report.append("")
                report.append("💡 Troubleshooting tips:")
                report.append("  • Check .env file has correct SQL_SERVER_NAME and SQL_DATABASE_NAME")
                report.append("  • Verify you have access to the database server")
                report.append("  • Try connecting manually with SQL Server Management Studio")
                report.append("  • Check Windows authentication or DB_USERNAME/DB_PASSWORD")
        else:
            report.append("❌ No connection string available")
            report.append("💡 Make sure .env file exists with database configuration")

        report.append("")

        # Schema validation
        if self.connection_string and self.test_connection():
            report.append("🔍 SCHEMA VALIDATION")
            report.append("-" * 40)
            actual_schema = self.discover_actual_schema()

            if actual_schema:
                # Show table name mappings first
                actual_tables_lower = {table.lower(): table for table in actual_schema.keys()}
                documented_found = []

                for doc_table in self.tables.keys():
                    if doc_table.lower() in actual_tables_lower:
                        actual_table = actual_tables_lower[doc_table.lower()]
                        if doc_table == actual_table:
                            documented_found.append(f"  ✅ {doc_table}")
                        else:
                            documented_found.append(f"  🔄 {doc_table} → {actual_table} (case mismatch)")

                if documented_found:
                    report.append("📋 DOCUMENTED TABLES FOUND:")
                    report.extend(documented_found)
                    report.append("")

                validation_issues = self.validate_documented_tables(actual_schema)
                if validation_issues:
                    report.append("⚠️ VALIDATION ISSUES:")
                    report.extend(validation_issues)
                else:
                    report.append("✅ All documented tables and key fields found")

                undocumented = self.find_undocumented_tables(actual_schema)
                if undocumented:
                    report.append(f"\n📋 UNDOCUMENTED TABLES ({len(undocumented)} found):")
                    # Group similar tables
                    interesting_tables = []
                    boring_tables = []

                    for table in undocumented[:20]:  # Show first 20
                        if any(keyword in table.lower() for keyword in
                               ['right', 'sales', 'inventory', 'price', 'product', 'customer', 'competitor', 'ebay',
                                'supplier']):
                            interesting_tables.append(f"  🎯 {table}")
                        else:
                            boring_tables.append(f"  • {table}")

                    if interesting_tables:
                        report.append("  📊 Potentially Interesting Tables:")
                        report.extend(interesting_tables[:10])

                    if boring_tables:
                        report.append("  📁 Other Tables:")
                        report.extend(boring_tables[:10])

                    if len(undocumented) > 20:
                        report.append(f"  ... and {len(undocumented) - 20} more")
                else:
                    report.append("✅ No significant undocumented tables found")
            else:
                report.append("❌ Could not retrieve database schema")
        else:
            report.append("⚠️ Skipping schema validation - no database connection")

        report.append("")

        # Relationship analysis
        report.append("🔗 RELATIONSHIP ANALYSIS")
        report.append("-" * 40)
        gaps = self.analyze_relationship_gaps()
        if gaps:
            for gap in gaps:
                report.append(f"  • {gap}")
        else:
            report.append("✅ No obvious relationship gaps found")

        report.append("")

        # Maintenance recommendations
        report.append("💡 MAINTENANCE RECOMMENDATIONS")
        report.append("-" * 40)
        recommendations = [
            "Update table names in database_plugin.py to match actual case (PMSalesPBI, eBayNF_SupplierMatch)",
            "Consider breaking database_plugin.py into modular query classes",
            "Implement automated schema drift detection",
            "Add query performance monitoring",
            "Create unit tests for all documented query patterns",
            "Set up regular validation of join relationships",
            "Document data lineage and update frequencies",
            "Create backup/rollback procedures for schema changes"
        ]

        for i, rec in enumerate(recommendations, 1):
            report.append(f"  {i}. {rec}")

        return "\n".join(report)

    def export_schema_json(self) -> str:
        """Export current schema as JSON for external tools"""
        schema_export = {
            'tables': {name: asdict(table) for name, table in self.tables.items()},
            'relationships': [asdict(rel) for rel in self.relationships],
            'export_timestamp': datetime.now().isoformat(),
            'version': '1.0'
        }
        return json.dumps(schema_export, indent=2)

    def generate_query_templates(self) -> Dict[str, str]:
        """Generate modular query templates"""
        templates = {}

        # Product-centric queries
        templates['product_360'] = """
-- Complete Product Analysis Template
SELECT 
    -- Sales Performance
    s.Product,
    SUM(s.Sales) as TotalRevenue,
    SUM(s.Quantity) as TotalUnits,
    COUNT(DISTINCT s.CustomerName) as CustomerCount,

    -- Inventory Status
    i.Qty as CurrentStock,
    i.Value as InventoryValue,
    i.DSI as DaysSupplyInventory,

    -- Performance Scores
    r.OverallScore,
    r.StockScore,
    r.CompScore

FROM PMSalesPBI s
LEFT JOIN rightInventory i ON s.Product = i.Product AND i.Status = 'Active'
LEFT JOIN rightScore_results r ON s.Product = r.Product
WHERE s.Product = '{product}'
GROUP BY s.Product, i.Qty, i.Value, i.DSI, r.OverallScore, r.StockScore, r.CompScore
        """

        templates['oean_360'] = """
-- Complete OEAN Market Intelligence Template
WITH ProductMapping AS (
    SELECT Product, [OE] as OEAN FROM rightStock_ProductOEs WHERE [OE] = '{oean}'
),
OurPerformance AS (
    SELECT p.Product, p.OEAN, SUM(s.Sales) as Revenue, SUM(s.Quantity) as Units
    FROM ProductMapping p
    LEFT JOIN PMSalesPBI s ON p.Product = s.Product
    GROUP BY p.Product, p.OEAN
),
MarketIntelligence AS (
    SELECT 
        '{oean}' as OEAN,
        o.[Dealer List Price] as MSRP,
        AVG(i.[Price]) as AvgCompetitorPrice,
        COUNT(i.[Competitor Name]) as CompetitorCount,
        COUNT(DISTINCT sup.[collection]) as SupplierCount,
        AVG(TRY_CONVERT(decimal(10,2), e.UnitPrice)) as AvgEbayPrice,
        COUNT(e.OEAN) as EbayListings
    FROM OEPriceBookPBI o
    LEFT JOIN InternetCompData i ON o.[Part Number] = i.[OEAN]
    LEFT JOIN Suppliers sup ON o.[Part Number] = sup.[OEAN]  
    LEFT JOIN ebayWT e ON o.[Part Number] = e.OEAN 
        AND TRY_CONVERT(decimal(10,2), e.UnitPrice) IS NOT NULL
    WHERE o.[Part Number] = '{oean}'
)
SELECT * FROM OurPerformance
CROSS JOIN MarketIntelligence
        """

        templates['customer_analysis'] = """
-- Customer Analysis Template
SELECT 
    CustomerName,
    COUNT(DISTINCT Product) as UniqueProducts,
    SUM(Sales) as TotalRevenue,
    SUM(Quantity) as TotalUnits,
    AVG(Sales/Quantity) as AvgUnitPrice,
    MIN(InvDate) as FirstPurchase,
    MAX(InvDate) as LastPurchase,
    COUNT(DISTINCT YEAR(InvDate)) as YearsActive
FROM PMSalesPBI 
WHERE UPPER(CustomerName) LIKE '%{customer}%'
GROUP BY CustomerName
ORDER BY TotalRevenue DESC
        """

        templates['inventory_optimization'] = """
-- Inventory Optimization Template
SELECT 
    i.Product,
    i.Site,
    i.Qty,
    i.Value,
    i.DSI,
    r.StockScore,
    r.OverallScore,
    CASE 
        WHEN i.Qty < 1.0 THEN 'OUT_OF_STOCK'
        WHEN i.Qty <= 2.0 THEN 'CRITICAL'
        WHEN i.Qty <= 5.0 THEN 'LOW'
        WHEN i.DSI > 365 THEN 'SLOW_MOVING'
        WHEN i.DSI > 180 THEN 'OVERSTOCKED'
        ELSE 'NORMAL'
    END as StockStatus
FROM rightInventory i
LEFT JOIN rightScore_results r ON i.Product = r.Product
WHERE i.Status = 'Active'
    AND (i.Qty <= 5.0 OR i.DSI > 180 OR r.StockScore <= 2)
ORDER BY 
    CASE 
        WHEN i.Qty < 1.0 THEN 1
        WHEN i.Qty <= 2.0 THEN 2
        WHEN r.StockScore <= 2 THEN 3
        ELSE 4
    END, i.Value DESC
        """

        return templates

    def suggest_query_optimizations(self) -> List[str]:
        """Suggest query pattern optimizations"""
        suggestions = []

        # Analyze large tables
        large_tables = [name for name, table in self.tables.items()
                        if 'Large' in table.size_estimate or 'Very Large' in table.size_estimate]

        if large_tables:
            suggestions.append(
                f"🚀 For large tables ({', '.join(large_tables)}), always use TOP N or specific WHERE clauses")

        # Check for potential performance issues
        if 'ebayWT' in self.tables:
            suggestions.append(
                "⚡ ebayWT queries should always include TRY_CONVERT for UnitPrice and filter non-NULL values")

        if 'InternetCompData' in self.tables:
            suggestions.append(
                "🔍 InternetCompData queries should use bracketed field names: [OEAN], [Competitor Name], [Price]")

        suggestions.append("📊 Consider creating indexed views for frequently joined table combinations")
        suggestions.append("⏱️ Add query execution time monitoring to identify slow patterns")

        return suggestions


def create_env_template():
    """Create a template .env file"""
    env_template = """# Voice SQL Database Configuration
# Copy this file to .env and update with your actual values

# Database Connection
SQL_SERVER_NAME=BI-SQL001
SQL_DATABASE_NAME=CRPAF

# Database Authentication (optional - uses Windows auth if not provided)
# DB_USERNAME=your_username
# DB_PASSWORD=your_password

# Server Configuration (for server_api.py)
VOICE_SQL_SERVER=http://BI-SQL001:8000
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Azure OpenAI Configuration (optional)
# AZURE_OPENAI_ENDPOINT=your_endpoint
# AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=your_deployment
# AZURE_TENANT_ID=your_tenant_id
# AZURE_CLIENT_ID=your_client_id
# AZURE_CLIENT_SECRET=your_client_secret

# Email Configuration (for monitoring)
# RELAY_IP=your_smtp_server
# SMTP_PORT=25
# MONITOR_FROM_EMAIL=voicesql-monitor@yourcompany.com
# MONITOR_TO_EMAILS=admin@yourcompany.com,dba@yourcompany.com
# EMAIL_ON_SUCCESS=false
# EMAIL_ON_FAILURE=true

# Logging
DEBUG=false
LOG_LEVEL=INFO
"""

    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_template)


def main():
    """Main function to run schema analysis and maintenance"""

    print("🗃️ Voice SQL Schema Maintenance Tool")
    print("=" * 60)

    # Check for .env file
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️ No .env file found. Creating template...")
        create_env_template()
        print("📝 Please update .env file with your database details and run again")
        return

    # Initialize analyzer
    print("🔧 Initializing schema analyzer...")
    analyzer = SchemaAnalyzer()

    # Generate maintenance report
    print("📊 Generating schema maintenance report...")
    report = analyzer.generate_maintenance_report()
    print("\n" + report)

    # Save report to file
    report_file = Path("schema_maintenance_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n💾 Report saved to: {report_file}")

    # Export schema as JSON
    schema_json = analyzer.export_schema_json()
    json_file = Path("voice_sql_schema.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        f.write(schema_json)
    print(f"💾 Schema exported to: {json_file}")

    # Generate query templates
    templates = analyzer.generate_query_templates()
    templates_file = Path("query_templates.sql")
    with open(templates_file, 'w', encoding='utf-8') as f:
        for name, template in templates.items():
            f.write(f"-- {name.upper()}\n")
            f.write(f"{template}\n")
            f.write("-" * 80 + "\n\n")
    print(f"💾 Query templates saved to: {templates_file}")

    # Show optimization suggestions
    suggestions = analyzer.suggest_query_optimizations()
    print("\n" + "=" * 60)
    print("🚀 OPTIMIZATION SUGGESTIONS")
    print("=" * 60)
    for suggestion in suggestions:
        print(suggestion)


if __name__ == "__main__":
    main()