import logging
import pyodbc
from faker import Faker

from .utils import table_exists, create_table, insert_record

logger = logging.getLogger(__name__)

# Trusted Connection string for internal CRP SQL Server
connection_string_template = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER={BI-SQL001};"
    "DATABASE={CRPAF};"
    "Trusted_Connection=yes;"
)


class Database:
    def __init__(self, server_name: str, database_name: str) -> None:
        self.conn = get_connection(server_name=server_name, database_name=database_name)

    def setup(self) -> None:
        logger.debug("Setting up the database.")
        cursor = self.conn.cursor()

        if table_exists(cursor):
            return

        logger.debug("Creating table.")
        create_table(cursor)

        fake = Faker()
        logger.debug("Generating and inserting records.")

        for i in range(1000):
            insert_record(cursor, i, fake)

        self.conn.commit()
        logger.debug("Database setup completed.")

    def query(self, query: str) -> [pyodbc.Row]:
        cursor = self.conn.cursor()
        try:
            logger.debug("Querying database with: {}.".format(query))
            cursor.execute(query)
            result = cursor.fetchall()
            logger.debug("Successfully queried database: {}.".format(result))
        except Exception as ex:
            logger.error("Error querying database: {}.".format(ex))
            return "No Result Found"
        finally:
            cursor.close()

        return result

def get_connection(server_name: str, database_name: str) -> pyodbc.Connection:
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server_name};"
        f"DATABASE={database_name};"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(connection_string)

