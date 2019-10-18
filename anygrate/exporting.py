from os.path import join
import psycopg2.extras
import logging
from os.path import basename
logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(basename(__file__))


def export_to_csv(tables, dest_dir, connection, extract_sql=None):
    """
    Export data using postgresql COPY
    extract_sql is an optional dict specifying a specific SQL to extract data.
    """
    csv_filenames = []
    extract_sql = extract_sql or {}
    for table in tables:
        filename = join(dest_dir, table + '.csv')
        with connection.cursor() as cursor, open(filename, 'w') as f:
            extract_from = extract_sql.get(table)
            if not extract_from:
                copy_expr = table
            elif extract_from.upper().startswith('SELECT '):
                copy_expr = "(" + extract_from + ")"
            else:
                copy_expr = "(SELECT * FROM %s WHERE %s)" % (
                    table, extract_from)
            cursor.copy_expert(
                "COPY %s TO STDOUT WITH CSV HEADER NULL ''" % copy_expr, f)
            csv_filenames.append(filename)
    return csv_filenames


def extract_existing(tables, m2m_tables, discriminators, connection):
    """ Extract data from the target db,
    focusing only on discriminator columns.
    Extracted data is a dict whose values are lists of named tuples:
    {'table': [{'value', 12}, ...], ...}
    It means you can get result['table'][0]['column']
    This function is used to get the list of data to update in the target db
    """
    result = {}
    for table in tables:
        result[table] = []
        columns = None
        if discriminators.get(table):
            columns = ', '.join(discriminators[table]) + ', id'
        elif table in m2m_tables:
            columns = '*'  # Note: no actual id value in this case!
        if columns:
            with connection.cursor(
                    cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute('select %s from %s' % (columns, table))
                data = cursor.fetchall()
            result[table] = data
    return result
