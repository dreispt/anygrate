import xmlrpclib

""" Method to find out the dependencies order to import of an OpenERP model
    Set excluded_models to None if there is no model to exclude.
    If you want to exclude some models, use the following syntax :
    excluded_models = ['res.currency', 'res.country']
"""


def get_ordre_importation(username, pwd, dbname, model, excluded_models=None,
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
    # print('model=%r path=%r' % (model, path))
    if excluded_models is not None:
        for excl_model in excluded_models:
            seen.add(excl_model)
        excluded_models = None
    seen.add(model)
    m2o = set()
    fields = sock.execute(dbname, uid, pwd, model, 'fields_get')
    for field in fields:
        if fields[field]['type'] == 'many2one':
            m = fields[field]['relation']
            # Cas des structures arborescentes (reflexives)
            if m in path:
                print('BOUCLE %s a un m2o %r vers %s, qui est un de ses ancetres (path=%r)' % (model, field, m, path))
            if m not in seen:
                m2o.add(m)
                seen.add(m)
    for m in m2o:
        res += get_ordre_importation(username, pwd, dbname, m,
                                     path=path+(model,), excluded_models=excluded_models, seen=seen)
    res.append(model)
    return res

for model in ('account.account', 'product.product'):
    print("Essai pour %r" % model)
    print(get_ordre_importation('admin', 'admin', 'ecox_db', model))
    print
