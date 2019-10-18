import psycopg2
import yaml
import logging
from os.path import basename

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(basename(__file__))


class Mapping(object):
    """
    Data structure describing the data source, data target,
    and the transformations needed.
    Does not intercat with any database.
    """
    # API
    mapping = {}
    deferred = {}
    extract_sql = {}
    fk2update = {}

    # Internal?
    #last_id = 1
    #new_id = 1
    last_ids = {}
    target_connection = None
    fk2update = None

    def __init__(self, modules, filenames):
        """
        Open the files and parse the mapping
        """
        full_mapping = {}
        # load the full mapping file
        for filename in filenames:
            with open(filename) as stream:
                full_mapping.update(yaml.load(stream))
        # filter to keep only wanted modules
        self.mapping = {}
        self.deferred = {}
        self.extract_sql = {}
        for module in modules:
            if module not in full_mapping:
                LOG.warn('Mapping is not complete: module "%s" is missing!', module)
                continue
            for source_column, target_columns in full_mapping[module].items():
                if '__' in source_column:
                    # skip special markers
                    continue
                if (target_columns in ('__forget__', False)
                        or self.mapping.get(source_column) == '__forget__'):
                    self.mapping[source_column] = '__forget__'
                    continue
                if target_columns is None:
                    target_columns = {}
                try:
                    self.mapping.setdefault(source_column, target_columns)
                    self.mapping[source_column].update(target_columns)
                except:
                    raise ValueError('Error in the mapping file: "%s" is invalid here'
                                     % repr(target_columns))

        # replace function bodies with real functions
        self.fk2update = {}
        for incolumn in self.mapping:
            targets = self.mapping[incolumn]
            if targets in (False, '__forget__'):
                self.mapping[incolumn] = {}
                continue
            for outcolumn, function in targets.items():
                if function in ('__copy__', '__moved__', None):
                    continue
                if function == '__defer__':
                    self.mapping[incolumn][outcolumn] = '__copy__'
                    table, column = outcolumn.split('.')
                    self.deferred.setdefault(table, set())
                    self.deferred[table].add(column)
                    continue
                if function.startswith('__fk__ '):
                    if len(function.split()) != 2:
                        raise ValueError('Error in the mapping file: "%s" is invalid in %s'
                                         % (repr(function), outcolumn))
                    self.fk2update[outcolumn] = function.split()[1]
                    self.mapping[incolumn][outcolumn] = '__copy__'
                    continue
                if function.startswith('__ref__'):
                    if len(function.split()) != 2:
                        raise ValueError('Error in the mapping file: "%s" is invalid in %s'
                                         % (repr(function), outcolumn))
                    # we handle that in the postprocess
                    self.mapping[incolumn][outcolumn] = function
                    continue
                function_body = "def mapping_function(self, source_row, target_rows):\n"
                if type(function) is not str:
                    raise ValueError('Error in the mapping file: "%s" is invalid in %s'
                                     % (repr(function), outcolumn))
                function_body += '\n'.join([4*' ' + line for line in function.split('\n')])
                mapping_function = None
                exec(compile(function_body, '<' + incolumn + ' → ' + outcolumn + '>', 'exec'),
                     globals().update({
                         'newid': lambda: self.newid(table),
                         'sql': self.sql}))
                self.mapping[incolumn][outcolumn] = mapping_function
                del mapping_function

        # build the discriminator mapping
        self.discriminators = {}
        for mapping in full_mapping.values():
            self.discriminators.update({
                key.split('.')[0]: value
                for key, value in mapping.items()
                if '__discriminator__' in key})
            # define query to pass to COPY instead of bare table name
            self.extract_sql.update({
                key.split('.')[0]: value
                for key, value in mapping.items()
                if '__query__' in key})

    def get_last_id(self, table):
        return self.last_ids.get(table, 0)

    def newid(self, table):
        """ increment the global stored last_id
        This method is available as a function in the mapping
        """
        self.last_ids.setdefault(table, 0)
        self.last_ids[table] += 1
        #self.new_id += 1
        #return self.new_id
        return self.last_ids[table]

    def sql(self, db, sql, args=()):
        """ execute an sql statement in the target db and return the value
        This method is available as a function in the mapping
        """
        assert db in ('source', 'target'), u"First arg of sql() should be 'source' or 'target'"
        connection = self.target_connection if db == 'target' else self.source_connection
        with connection.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall() if 'select ' in sql.lower() else ()

    def get_targets(self, source):
        """ Return the target mapping for a column or table
        """
        if '.' in source:  # asked for a column
            table, column = source.split('.')
            mapping = self.mapping.get(source, None)
            # not found? We look for wildcards
            if mapping is None:
                # wildcard, we match the source
                if '.*' in self.mapping:
                    return {source: None}
                # partial wildcard, we match only for the table
                partial_pattern = '%s.*' % table
                if partial_pattern in self.mapping:
                    if self.mapping[partial_pattern]:
                        return {k.replace('*', column): v
                                for k, v in self.mapping[partial_pattern].items()}
                    return {source: None}
            return mapping

        else:  # asked for a table
            self.target_tables = set()
            target_fields = [t[1] for t in self.mapping.items() if t[0].split('.')[0] == source]
            for f in target_fields:
                self.target_tables.update([c.split('.')[0] for c in f.keys()])
            self.target_tables = list(self.target_tables)
            return self.target_tables

    def get_sources(self, target=None):
        """ Return the source tables given a target table
            If none, return all mapped source tables.
        """
        res = {t[0].split('.')[0]
               for t in self.mapping.items()
               if not target
               or target in [
                   c.split('.')[0]
                   for c in type(t[1]) is dict and t[1].keys() or ()]}
        return sorted(list(res))

    def update_last_id(self, source_tables, source_connection, target_tables, target_connection):
        """ update the last_id with max of source and target dbs
        """
        self.target_connection = target_connection
        self.source_connection = source_connection
        for source_table in source_tables:
            with source_connection.cursor() as c:
                # FIXME the key (id) shouldn't be hardcoded below
                try:
                    c.execute('select max(id) from %s' % source_table)
                    maxid = c.fetchone()
                    self.last_ids[source_table] = max(
                        maxid and maxid[0] or 0,
                        self.last_ids.get(source_table, 0))
                except psycopg2.ProgrammingError:
                    # id column does not exist
                    source_connection.rollback()
        for target_table in target_tables:
            with target_connection.cursor() as c:
                # FIXME the key (id) shouldn't be hardcoded below
                try:
                    c.execute('select max(id) from %s' % target_table)
                    maxid = c.fetchone()
                    self.last_ids[target_table] = max(
                        maxid and maxid[0] or 0,
                        self.last_ids.get(target_table, 0))
                except psycopg2.ProgrammingError:
                    # id column does not exist
                    target_connection.rollback()
        #self.new_id = 10 * self.last_id  # FIXME 10 is arbitrary but should be enough
