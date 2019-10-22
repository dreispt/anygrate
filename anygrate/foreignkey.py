import psycopg2


class DatabaseKeyMap(object):
    """
    Stores id ket mappings between source and target records.
    Note that the target record could be in a different table from the source.

    When data is reshaped to the target structure, table keys
    are mapped to new ids, and this map is stored.
    Cases:
    - target is same table:
      - assign new or existing id
      - remap all FKs at destination
    - target is different table
      - assign new or existing id
      - remap all FKs at destination


    Assign ID
    =========
    There are two cases to map keys to target database:
    new records and existing records.

    Naive implementation stores data in an in memory dict.
    This could be a problem for large databases.
    To consider an alternate implementation using a datatabase for
    this storage (SQLite, PostgreSQL itself).

    Get ID
    ======
    Used to process FK values (and dynamic reference values).
    """

    _last_ids = {}
    _existing_discriminators = {}  # discriminator ids at target
    _key_map = {}  # From source id to target id

    def __init__(self, target_tables, discriminators, target_conn):
        """
        Initialize the data needed to assign ids.
        @param target_tables:   list of target table names
        @param discriminators:  dict mapping table names and column name tuples
        @param target_conn:     conenction object for the target database
        @return nothing (setups internal state)
        """
        for table in target_tables:
            self._init_last_ids(table, target_conn)
            discriminator = discriminators.get(table)
            if discriminator:
                self._init_discriminators(table, discriminator, target_conn)
            self._key_map[table] = {}  # prepare to record assigned keys

    def _init_discriminators(self, target_table, discriminator, target_conn):
        """
        Returns a dict mapping source ids into target ids
        """
        discriminator_columns = ", ".join(discriminator)
        with target_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as c:
            c.execute(
                "select id, %s from %s" %
                (discriminator_columns, target_table))
            data = c.fetchall()
        existing_discriminators = {}
        for row in data:
            key = tuple(str(x) for x in row[1:])
            value = row[0]
            existing_discriminators[key] = value
        self._existing_discriminators[target_table] = existing_discriminators
        return existing_discriminators

    def _init_last_ids(self, target_table, target_conn):
        result = 0
        with target_conn.cursor() as c:
            c.execute("""
                select count(*)
                from information_schema.columns
                where column_name = 'id'
                and table_name = %s
                """, (target_table, ))
            has_id = int(c.fetchone()[0])
            if has_id:
                c.execute("select max(id) from %s" % target_table)
                result = int(c.fetchone()[0] or 0)
        self._last_ids[target_table] = result
        return result

    def _source_key(self, source_id, source_table=None):
        """
        String to be used as key for the key map stored data.
        Usually it is just the original id, in string format.
        In some cases we need to also annotate the source table.
        For example, when a row moved between tables.
        """
        source_id = str(source_id)
        if source_table:
            source_id += "@" + source_table
        return source_id

    def set_id(self, target_id, target_table, source_id, source_table=None):
        if target_id and source_id != target_id:
            source_table = source_table or target_table
            source_key = self._source_key(
                source_id, target_table and target_table != source_table)
            self._key_map[target_table][source_key] = target_id

    def assign_existing_id(
        self, source_id, source_table, target_table, discriminator_value=None
    ):
        """
        Try to assign an existing target ID to a record,
        using a discriminator value to lookup thetarget table.

        This source to target mapping is stored internally,
        for later retrieval when remapping the target database FKs.

        This method requires previous preparation of data:
        - target table known discriminator data
        """
        target_id = None
        if discriminator_value:
            existing = self._existing_discriminators.get(target_table, {})
            target_id = existing.get(discriminator_value)
        self.set_id(target_id, target_table, source_id, source_table)
        return target_id

    def assign_new_id(
        self, source_id, source_table, target_table
    ):
        """
        Assign the next available ID in the target table.

        This source to target mapping is stored internally,
        for later retrieval when remapping the target database FKs.

        This method required prevous preparation of data:
        - target table last used ids
        """
        target_id = self._last_ids.get(target_table, 0) + 1
        self._last_ids[target_table] = target_id
        self.set_id(target_id, target_table, source_id, source_table)
        return target_id

    def get_id(self, key, target_table):
        """
        Look up target key ID for an original source ID.
        Used to remap FK values on the target database.
        Source ID is the original id to look up.

        Source table should also be provided, and is needed for the cases
        where the row moved to a different table.
        """
        if not target_table in self._key_map:
            # TODO: change Print to a Log message
            print('WARNING: %s not found on Key Map' % target_table)
            return key
        key_map = self._key_map[target_table]
        target_id = key_map.get(key)
        if not target_id and '@' in key:
            target_id = key_map.get(key.split("@")[0])
        return target_id
