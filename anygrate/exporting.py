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
        with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            if table not in discriminators:
                continue
            columns = discriminators[table]
            id_column = ['id'] if table not in m2m_tables else []
            cursor.execute('select %s from %s' % (', '.join(columns + id_column), table))
            result[table] = cursor.fetchall()
    return result


def get_discriminations(main_tables, m2m_tables, discriminators,
                        src_conn, targ_conn):
    """ Extract data from the target db,
    focusing only on discriminator columns.
    Extracted data is a dict whose values are lists of named tuples:
    {'table': [{'value', 12}, ...], ...}
    It means you can get result['table'][0]['column']
    This function is used to get the list of data to update in the target db
    """
    result = {}

    for table in main_tables:
        columns = discriminators.get(table)
        if not columns or table in m2m_tables or 'id' in columns:
            continue
        connection = targ_conn  #FIXME: src_conn if 'id' in columns else targ_conn
        # print("Discriminators:", table, columns)
        cols = ', '.join(columns)
        sql = 'select %s, min(id) id from %s group by %s' % (
            cols, table, cols)
        with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute(sql)
            cols = [desc[0] for desc in c.description]
            data = c.fetchall()
        # regular table: will map (udpate ids) to target rows
        result[table] = {
            tuple([str(f) for f in x[:-1]]): str(x[-1])
            for x in data}
        count = len(result[table])
        print(result.get(table, {}))
        LOG.debug("Existing %s: %d rows" % (table, count))

    for table in m2m_tables:
        result[table] = []
        connection = targ_conn
        sql = 'select * from %s' % table
        with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute(sql)
            cols = [desc[0] for desc in c.description]
            data = c.fetchall()
        # m2m table: will avoid importing duplicate rows
        result[table] = {
            tuple([str(row[cols.index(f)]) for f in sorted(cols)]): 0
            for row in data}
        count = len(result[table])
        print(result.get(table, {}))
        LOG.debug("Existing %s: %d rows" % (table, count))

    return result
