import xmlrpclib

""" Method to find out the dependencies order to import of an OpenERP model
    Set excluded_models to None if there is no model to exclude.
    If you want to exclude some models, use the following syntax :
    excluded_models = ['res.currency', 'res.country']
"""


def get_ordre_importation(username, pwd, dbname, models, excluded_models=None,
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
        #print("LECTURE DU MODELE %r " % model)
        #print
        seen.add(model)
        fields = sock.execute(dbname, uid, pwd, model, 'fields_get')
        for field in fields:
            if fields[field]['type'] == 'many2one':
                m = fields[field]['relation']
                # Cas des structures arborescentes (reflexives)
                #if m in path:
                    #print(' BOUCLE %s a un m2o %r vers %s, qui est un de ses '
                    #      'ancetres (path=%r)' % (model, field, m, path))
                if m not in seen:
                    m2o.add(m)
                    seen.add(m)
            if fields[field]['type'] == 'many2many' and 'related_columns' in fields[field]:
                m = fields[field]['relation']
                third_table = fields[field]['third_table']
                #print(" M2M vers %r THIRD_TABLE : %r" % (m,
                #      third_table))
                # Cas des structures arborescentes (reflexives)
                #if m in path:
                    #print(' BOUCLE %s a un m2m %r vers %s, qui est un de ses '
                    #      'ancetres (path=%r)' % (model, field, m, path))
                if m not in seen:
                    m2m.add(m)
                    seen.add(m)
                if third_table not in seen:
                    related_tables.add(third_table)
                    seen.add(third_table)

        for m in m2m:
            res += get_ordre_importation(username, pwd, dbname, (m,),
                                         path=path+(model,),
                                         excluded_models=excluded_models, seen=seen)
        for m in m2o:
            res += get_ordre_importation(username, pwd, dbname, (m,),
                                         path=path+(model,),
                                         excluded_models=excluded_models, seen=seen)

    res.append(model)
    if related_tables:
        for table in related_tables:
            res.append(table)
    return res

print(get_ordre_importation('admin', 'admin', 'ecox_db',('res.groups',),['ir.module.category'], None))
print(get_ordre_importation('admin', 'admin', 'ecox_db',('res.groups',),None, None))
