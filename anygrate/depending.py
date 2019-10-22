import xmlrpc
import logging
from os.path import basename


logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(basename(__file__))


def add_related_tables(target_connection, tables, excluded_tables):
    """
    From a list of tables, look at FKs for dependant tables.
    Also look for m2m relation tables involving all the selected tables.

    - Find all FK dependant tables 
    - TODO: recursively navigate FKs to expand the list of tables
    """
    def _get_fk_dependencies_dict(cursor, tables, excluded_tables,
                                  all_deps=None):
        all_deps = all_deps or {x: set() for x in tables}
        if tables:
            excluded_tables = excluded_tables or []
            cursor.execute("""
                SELECT DISTINCT ccu.table_name, tc.table_name parent
                FROM information_schema.table_constraints AS tc
                  JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE constraint_type = 'FOREIGN KEY'
                  AND NOT LEFT(ccu.table_name, 3) = 'ir_'
                  /* Don't follow down the dependencies from these tables */
                  AND NOT tc.table_name IN (
                    'res_users', 'res_company', 'res_country', 'res_currency')
                  AND tc.table_name = ANY(%s)
                  AND NOT ccu.table_name = ANY(%s)
                ORDER BY 1;""", (list(tables), list(all_deps)))
            data = cursor.fetchall()
            new_deps = set()
            for table, parent in data:
                if table not in excluded_tables:
                    new_deps.add(table)
                    all_deps.setdefault(table, set())
                    all_deps[table].add(parent)
            all_deps = _get_fk_dependencies_dict(
                cursor, new_deps, excluded_tables + list(tables), all_deps)
        return all_deps

    def _get_m2m_dependencies_set(cursor, tables, excluded_tables):
        cursor.execute("""
            SELECT DISTINCT tc.table_name, ccu.table_name
            FROM information_schema.table_constraints AS tc
              JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_catalog = current_database()
              AND tc.table_name NOT IN (
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name='id')
            ORDER BY 1, 2;
        """)
        all_m2m = dict()
        for table, dependant in cursor.fetchall():
            all_m2m.setdefault(table, set())
            all_m2m[table].add(dependant)
        m2m_tables = set(
            k for k, v in all_m2m.items()
            if v.issubset(tables) and k not in (excluded_tables or []))
        return m2m_tables

    with target_connection.cursor() as cursor:
        model_tables = _get_fk_dependencies_dict(
            cursor, tables, excluded_tables).keys()
        m2m_tables = _get_m2m_dependencies_set(
            cursor, tables, excluded_tables)
    return model_tables, m2m_tables


def get_fk_to_update(connection, tables):
    """ Method to get back all columns referencing another table
    """
    # ccu = referenced table and key (ex: res_company.id)
    # |_ tc = FK constraint and referencing table
    #    |_ kcu = FK columns referencing a key (ex: res_company.parent_id)
    query = """
    SELECT kcu.table_name, kcu.column_name, ccu.table_name as referenced
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        data = cursor.fetchall()
        result = {
            row[0] + '.' + row[1]: row[2]
            for row in data
        }
    return result


def get_mapping_migration(username_from, username_to, pwd_from, pwd_to,
                          dbname_from, dbname_to, model):
    """ Method to define which record needs to be update or not before importing it
    """
    sock_from, uid_from = get_socket(username_from, pwd_from, dbname_from, 8069)
    sock_to, uid_to = get_socket(username_to, pwd_to, dbname_to, 8169)
    mapping_xml_id = {}
    mapping_list = []
    for m in model:

        records_source = sock_from.execute(dbname_from, uid_from, pwd_from,
                                           'ir.model.data', 'search',
                                           [('model', '=', m)])
        if records_source:
            for r in records_source:
                xml_id_source = get_xml_id_source(r, username_from, pwd_from,
                                                  dbname_from, m)

                xml_id_destination = get_xml_id_destination(xml_id_source,
                                                            username_to, pwd_to,
                                                            dbname_to, m)
                if xml_id_destination:
                    if (xml_id_source['name'] == xml_id_destination['name']
                            and xml_id_source['id'] != xml_id_destination['id']):
                        data = {
                            'xml_id': xml_id_source['name'],
                            'res_id_source': xml_id_source['id'],
                            'res_id_destination': xml_id_destination['id'],
                        }
                        mapping_list.append(data)
                else:
                    print('XML_ID NOT FOUND')
        mapping_xml_id[m] = mapping_list


def get_destination_id(source_id, username_from, username_to, pwd_from, pwd_to,
                       dbname_from, dbname_to, model):

    sock_from, uid_from = get_socket(username_from, pwd_from, dbname_from, 8069)
    sock_to, uid_to = get_socket(username_to, pwd_to, dbname_to, 8169)

    id_model_data = get_xml_id_source(source_id, username_from, username_to,
                                      pwd_from, pwd_to, dbname_from,
                                      dbname_to, model)
    if id_model_data:

        destination_id = sock_to.execute(dbname_to, uid_to, pwd_to,
                                         'ir.model.data', 'read',
                                         id_model_data, ['res_id'])
        return destination_id
    return None


def get_xml_id_source(source_id, username_source, pwd_source,
                      dbname_from, model):

    sock_from, uid_from = get_socket(username_source, pwd_source, dbname_from, 8069)
    xml_id_source = sock_from.execute(dbname_from, uid_from, pwd_source,
                                      'ir.model.data', 'read',
                                      source_id, ['name'])
    if xml_id_source:
        return xml_id_source
    else:
        return None


def get_xml_id_destination(xml_id_source, username_to, pwd_to, dbname_to,
                           model):

    sock_to, uid_to = get_socket(username_to, pwd_to, dbname_to, 8169)
    xml_id_source = xml_id_source['name']
    id_model_data = sock_to.execute(dbname_to, uid_to, pwd_to,
                                    'ir.model.data', 'search',
                                    [('name', '=', xml_id_source)])
    if id_model_data:
        xml_id_data = sock_to.execute(dbname_to, uid_to, pwd_to,
                                      'ir.model.data',
                                      'read', id_model_data,
                                      ['name'])
        return xml_id_data[0]
    return None


def get_socket(username, pwd, dbname, port):

    str_common = 'http://localhost:%s/xmlrpc/common' % port
    str_object = 'http://localhost:%s/xmlrpc/object' % port
    sock_common = xmlrpc.client.ServerProxy(str_common)
    uid = sock_common.login(dbname, username, pwd)
    sock = xmlrpc.client.ServerProxy(str_object)
    return sock, uid
