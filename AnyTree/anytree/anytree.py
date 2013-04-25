import xmlrpclib
import argparse
import psycopg2

""" Method to find out the dependencies order to import of an OpenERP model
    Set excluded_models to None if there is no model to exclude.
    If you want to exclude some models, use the following syntax :
    excluded_models = ['res.currency', 'res.country']
"""
parser = argparse.ArgumentParser(description='Return the dependencies order'
                                             ' of models give as parameters')

parser.add_argument('-m', '--models', nargs='+', help="One or many models",
                    required=True)
parser.add_argument('-d', '--db_name',
                    help="Name of the database to connect to",
                    required=True)
parser.add_argument('-u', '--user',
                    help="Name of the user to log into the database with",
                    required=True)
parser.add_argument('-p', '--pwd',
                    help="Password of the previous user",
                    required=True)
parser.add_argument('-x', '--excluded', nargs='+', help="One or many models"
                    " to exclude", required=False, default=None)

args = parser.parse_args()

username = args.user
pwd = args.pwd
dbname = args.db_name
models = args.models
excluded_models = args.excluded


def get_ordre_importation(username, pwd, dbname, models, excluded_models,
                          path=None, seen=None):
    # XML-RPC
    sock_common = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/common')
    uid = sock_common.login(dbname, username, pwd)
    sock = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/object')
    res = []
    if seen is None:
        seen = set()
    if path is None:
        path = ()
    if excluded_models is not None:
        for excl_model in excluded_models:
            seen.add(excl_model)
        excluded_models = None
    m2o = set()
    m2m = set()
    related_tables = set()
    for model in models:
        seen.add(model)
        fields = sock.execute(dbname, uid, pwd, model, 'fields_get')
        for field in fields:
            if fields[field]['type'] == 'many2one':
                m = fields[field]['relation']
                # Cas des structures arborescentes (reflexives)
                if m in path:
                    print(' BOUCLE %s a un m2o %r vers %s, qui est un de ses '
                          'ancetres (path=%r)' % (model, field, m, path))
                if m not in seen:
                    m2o.add(m)
                    seen.add(m)
            if fields[field]['type'] == 'many2many' and 'related_columns' in fields[field]:
                m = fields[field]['relation']
                third_table = fields[field]['third_table']
                print(" M2M vers %r THIRD_TABLE : %r" % (m,
                      third_table))
                # Cas des structures arborescentes (reflexives)
                if m in path:
                    print(' BOUCLE %s a un m2m %r vers %s, qui est un de ses '
                          'ancetres (path=%r)' % (model, field, m, path))
                if m not in seen:
                    m2m.add(m)
                    seen.add(m)
                if third_table not in seen:
                    related_tables.add(third_table)
                    seen.add(third_table)

        for m in m2m:
            res += get_ordre_importation(username, pwd, dbname, (m,),
                                         path=path+(model,),
                                         excluded_models=excluded_models,
                                         seen=seen)
        for m in m2o:
            res += get_ordre_importation(username, pwd, dbname, (m,),
                                         path=path+(model,),
                                         excluded_models=excluded_models,
                                         seen=seen)

    res.append(model)
    if related_tables:
        for table in related_tables:
            res.append(table)
    return res


def get_mapping_migration(username, pwd, dbname, model):

    #conn = psycopg2.connect(database=dbname, user='fjouatte', password='')
    #cur = conn.cursor()
    sock_common = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/common')
    uid = sock_common.login(dbname, username, pwd)
    sock = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/object')
    for m in model:
        #m = m.replace('.', '_')
        records = sock.execute(dbname, uid, pwd, 'ir.model.data', 'search',
                               [('model', '=', m)])
        print(records)
        #select_query = "SELECT * FROM %s;" %m
        #cur.execute(select_query)
        #cur.fetchone()
    #conn.commit()
    #cur.close()
    #conn.close()

get_mapping_migration(username, pwd, dbname, models)
#get_ordre_importation(username, pwd, dbname, models, excluded_models)
