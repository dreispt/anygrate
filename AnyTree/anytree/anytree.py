import xmlrpclib

""" Method to find out the dependencies order to import of an OpenERP model """


def get_ordre_importation(username, pwd, dbname, model, seen):

    # XML-RPC
    sock_common = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/common')
    uid = sock_common.login(dbname, username, pwd)
    sock = xmlrpclib.ServerProxy('http://localhost:8069/xmlrpc/object')

    res = []
    if seen is None:
        seen = set()
    seen.add(model)
    m2o = set()
    deps = set()
    fields = sock.execute(dbname, uid, pwd, model, 'fields_get')
    for field in fields:
        if fields[field]['type'] == 'many2one':
            m = fields[field]['relation']
            deps.add(m)
            # Cas des structures arborescentes (reflexives)
            if m not in seen:
                m2o.add(m)
                seen.add(m)
    for m in m2o:
        res += get_ordre_importation(username, pwd, dbname, m, seen)
    res.append(model)
    return res

