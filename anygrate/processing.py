import csv
import logging
import os
from os.path import basename, join, splitext

HERE = os.path.dirname(__file__)
logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(basename(__file__))

# increase the maximum csv field size. Hardcode it for the time being
# See https://bitbucket.org/anybox/anybox.migration.openerp/issue/2/
csv.field_size_limit(20971520)


class CSVProcessor(object):
    """ Take a csv file, process it with the mapping
    and output a new csv file
    """
    def __init__(self, mapping, fk2update=None):

        self.fk2update = fk2update or {}  # foreign keys to update during postprocessing
        self.mapping = mapping  # mapping.Mapping instance
        self.target_columns = {}
        self.writers = {}
        self.updated_values = {}
        self.fk_mapping = {}  # mapping for foreign keys
        self.ref_mapping = {}  # mapping for references
        self.lines = 0
        self.is_moved = set()
        ###self.existing_records = {}
        ###self.existing_records_without_id = {}

    def get_target_columns(self, filepaths):
        """ Compute target columns with source columns + mapping
        """
        if self.target_columns:
            return self.target_columns
        for filepath in filepaths:
            source_table = basename(filepath).rsplit('.', 1)[0]
            with open(filepath) as f:
                source_columns = csv.reader(f).next()
            for source_column in source_columns + ['_']:
                mapping = self.mapping.get_targets('%s.%s' % (source_table, source_column))
                # no mapping found, we warn the user
                if mapping is None:
                    origin = source_table + '.' + source_column
                    LOG.warn('No mapping definition found for column %s', origin)
                    continue
                if mapping == '__copy__':
                    continue
                elif mapping in (False, '__forget__'):
                    continue
                else:
                    for target in mapping:
                        t, c = target.split('.')
                        self.target_columns.setdefault(t, set()).add(c)

        self.target_columns = {k: sorted([c for c in v if c != '_'])
                               for k, v in self.target_columns.items()}
        return self.target_columns

    def set_existing_data(self, existing_records):
        """let the existing data be accessible during processing
        """
        self.existing_records = existing_records
        # the same without ids
        self.existing_records_without_id = {
            table: [{k: str(v) for k, v in nt.iteritems() if k != 'id'} for nt in existing]
            for table, existing in existing_records.iteritems()
        }

    def reorder_with_discriminators(self, tables):
        """ Reorder the filepaths based on tables pointed by discriminators
        (if they are fk)
        """
        # get the list of tables pointed by discriminators
        discriminator_tables = set()
        for table, columns in self.mapping.discriminators.iteritems():
            for column in columns:
                field = table + '.' + column
                if field in self.fk2update:
                    discriminator_tables.add(self.fk2update[field])
        # remove them from the initial tables
        tables = [t for t in tables if t not in discriminator_tables]
        # reorder the small set with a very basic algorithm:
        # put at left those without fk discriminator, right others
        ordered_tables = []
        for table in discriminator_tables:
            for column in self.mapping.discriminators.get(table, ()):
                field = table + '.' + column
                if table in ordered_tables:
                    continue
                if field in self.fk2update:
                    ordered_tables.append(table)
                else:
                    ordered_tables.insert(0, table)
        # append the two lists
        ordered_tables += tables
        return ordered_tables

    def process(self, source_dir, source_filenames, target_dir,
                target_connection, discriminations):
        """ The main processing method
        """
        # compute the target columns
        filepaths = [join(source_dir, source_filename) for source_filename in source_filenames]
        source_tables = [splitext(basename(path))[0] for path in filepaths]
        self.target_columns = self.get_target_columns(filepaths)
        # load discriminator values for target tables
        # TODO

        # filenames and files
        target_filenames = {
            table: join(target_dir, table + '.target.csv')
            for table in self.target_columns
        }
        target_files = {
            table: open(filename, 'ab')
            for table, filename in target_filenames.items()
        }
        self.writers = {t: csv.DictWriter(f, self.target_columns[t], delimiter=',')
                        for t, f in target_files.items()}
        for writer in self.writers.values():
            writer.writeheader()

        # update filenames and files
        update_filenames = {
            table: join(target_dir, table + '.update.csv')
            for table in self.target_columns
        }
        update_files = {
            table: open(filename, 'ab')
            for table, filename in update_filenames.items()
        }
        self.updatewriters = {t: csv.DictWriter(f, self.target_columns[t], delimiter=',')
                              for t, f in update_files.items()}
        for writer in self.updatewriters.values():
            writer.writeheader()
        LOG.info(u"Processing CSV files...")
        # We should first reorder the processing so that tables pointed to by
        # discriminator values which are fk be processed first. This is not the
        # most common case, but otherwise offsetting these values may fail,
        # leading to unwanted matching and unwanted merge.
        ordered_tables = self.reorder_with_discriminators(source_tables)
        ordered_paths = [join(source_dir, table + '.csv') for table in ordered_tables]
        for source_filepath in ordered_paths:
            self.process_one(source_filepath, target_connection, discriminations)
        # close files
        for target_file in target_files.values():
            target_file.close()
        for update_file in update_files.values():
            update_file.close()

        # POSTPROCESS target filenames and files
        target2_filenames = {
            table: join(target_dir, table + '.target2.csv')
            for table in self.target_columns
        }
        target2_files = {
            table: open(filename, 'ab')
            for table, filename in target2_filenames.items()
        }
        self.writers = {t: csv.DictWriter(f, self.target_columns[t], delimiter=',')
                        for t, f in target2_files.items()}
        for writer in self.writers.values():
            writer.writeheader()
        LOG.info(u"Postprocessing CSV files...")
        for filename in target_filenames.values():
            filepath = join(target_dir, filename)
            self.postprocess_one(filepath, discriminations)
        for f in target2_files.values():
            f.close()

        # POSTPROCESS update filenames and files
        update2_filenames = {
            table: join(target_dir, table + '.update2.csv')
            for table in self.target_columns
        }
        update2_files = {
            table: open(filename, 'ab')
            for table, filename in update2_filenames.items()
        }
        self.writers = {t: csv.DictWriter(f, self.target_columns[t], delimiter=',')
                        for t, f in update2_files.items()}
        for writer in self.writers.values():
            writer.writeheader()
        for filename in update_filenames.values():
            filepath = join(target_dir, filename)
            self.postprocess_one(filepath, discriminations)
        # close files
        for f in update2_files.values():
            f.close()

    def process_one(self, source_filepath,
                    target_connection, discriminations):
        """ Process one csv file
        The fk_mapping should not be read in this method. Only during postprocessing,
        Because the processing order is not determined (unordered dicts)
        """
        count_ins, count_upd = 0, 0
        source_table = basename(source_filepath).rsplit('.', 1)[0]
        with open(source_filepath, 'rb') as source_csv:
            reader = csv.DictReader(source_csv, delimiter=',')
            # process each csv line
            for source_row in reader:
                self.lines += 1
                target_rows = {}
                # process each column (also handle '_' as a possible new column)
                source_row.update({'_': None})
                for source_column in source_row:
                    mapping = self.mapping.get_targets(source_table + '.' + source_column)
                    if mapping is None:
                        continue
                    # we found a mapping, use it
                    for target_record, function in mapping.items():
                        target_table, target_column = target_record.split('.')
                        target_rows.setdefault(target_table, {})
                        if target_column == '_':
                            continue
                        if function in (None, '__copy__'):
                            # mapping is None: use identity
                            target_rows[target_table][target_column] = source_row[source_column]
                        elif type(function) is str and function.startswith('__ref__'):
                            target_rows[target_table][target_column] = source_row[source_column]
                            model_column = function.split()[1]
                            self.ref_mapping[target_record] = model_column

                        elif function in (False, '__forget__'):
                            # mapping is False: remove the target column
                            del target_rows[target_table][target_column]
                        # in case the id has moved to a new record,
                        # we should save the mapping to correctly fix fks
                        # This can happen in case of semantic change like res.partner.address
                        elif function == '__moved__':
                            self.is_moved.add(source_table)
                            newid = self.mapping.newid()
                            target_rows[target_table][target_column] = newid
                            self.fk_mapping.setdefault(source_table, {})
                            self.fk_mapping[source_table][int(source_row[source_column])] \
                                = newid + self.mapping.last_id
                        else:
                            # mapping is supposed to be a function
                            result = function(self, source_row, target_rows)
                            target_rows[target_table][target_column] = result

                # offset all ids except existing data and choose to write now or update later
                for table, target_row in target_rows.items():
                    if not any(target_row.values()):
                        continue
                    # if the line exists in the target db, we don't offset and write to update file
                    # (we recognize by matching the dict of discriminator values against existing)
                    ###existing = self.existing_records.get(table, [])
                    ###existing_without_id = self.existing_records_without_id.get(table, [])
                    ###discriminator_values = {d: target_row[d] for d in (discriminators or [])}
                    discriminators = sorted(self.mapping.discriminators.get(table, {}))
                    discriminator_value = tuple([target_row[x] for x in discriminators])
                    existing_id = int(discriminations.get(table, {}).get(discriminator_value, '0'))
                    row_id = target_row.get('id')
                    # print(discriminators, discriminator_value, existing_id, row_id)
                    # before matching existing, we should fix the discriminator_values which are fk
                    #### FIXME refactor and merge with the code in postprocess
                    ###for key, value in discriminator_values.items():
                    ###    fk_table = self.fk2update.get(table + '.' + key)
                    ###    if value and fk_table:
                    ###        value = int(value)
                    ###        # this is BROKEN because it needs the fk_table to be processed before.
                    ###        if value in self.fk_mapping.get(fk_table, []):
                    ###            discriminator_values[key] = str(
                    ###                self.fk_mapping[fk_table].get(value, value))
                    if row_id and existing_id:
                        # write to .update.csv
                        # save the mapping between source id and existing id
                        # we save the match between source and existing id
                        # to be able to update the fks in the 2nd pass
                        # if row_id != existing_id:
                        self.fk_mapping.setdefault(table, {})
                        self.fk_mapping[table][int(row_id)] = existing_id
                        # fix fk to a moved table with existing data
                        if source_table in self.is_moved:
                            source_id = int(source_row['id'])
                            if source_id in self.fk_mapping[source_table]:
                                target_row['id'] = existing_id
                                self.fk_mapping[source_table][source_id] = existing_id
                        self.updatewriters[table].writerow(target_row)
                        count_upd += 1

                    else:
                        # write to .target.csv
                        # offset the id of the line, except for m2m (no id)
                        if 'id' in target_row:
                            if 'id' not in discriminators:  # else keep id
                                target_row['id'] = int(row_id) + self.mapping.last_id
                            ###else:
                            # add to relations map
                            self.fk_mapping.setdefault(table, {})
                            self.fk_mapping[table][int(row_id)] = int(row_id)
                            if table.startswith('note_note'): print(row_id, target_row['id']) #FIXME
                            # handle deferred records
                            if table in self.mapping.deferred:
                                upd_row = {k: v for k, v in target_row.iteritems()
                                           if k == 'id'
                                           or (k in self.mapping.deferred[table] and v != '')}
                                if len(upd_row) > 1:
                                    self.updatewriters[table].writerow(upd_row)
                                for k in self.mapping.deferred[table]:
                                    if k in target_row:
                                        del target_row[k]
                        # don't write incomplete m2m
                        if ('id' not in target_row
                                and len(target_row) == 2
                                and not all(target_row.values())):
                            continue
                        # otherwise write the target csv line
                        self.writers[table].writerow(target_row)
                        count_ins += 1
                    #if table == 'note_stage_rel': print(target_row) #FIXME
        LOG.debug("Processed\t%s:\t%d ins\t%d upd"
                  % (source_table, count_ins, count_upd))

    def postprocess_one(self, target_filepath, discriminations):
        """ Postprocess one target csv file
        """
        __debug = 'note_stage'
        counter = 0
        table = basename(target_filepath).rsplit('.', 2)[0]
        m2m_rows = []
        with open(target_filepath, 'rb') as target_csv:
            reader = csv.DictReader(target_csv, delimiter=',')
            for target_row in reader:
                counter += 1
                postprocessed_row = {}
                # fix the foreign keys of the line
                for key, value in target_row.items():
                    target_record = table + '.' + key
                    postprocessed_row[key] = value
                    # if this is a fk, fix it
                    fk_table = self.fk2update.get(target_record)
                    if value and fk_table:
                        # if the target record is an existing record it should be in the fk_mapping
                        # so we restore the real target id, or offset it if not found
                        value = int(value)
                        postprocessed_row[key] = self.fk_mapping.get(fk_table, {}).get(
                            value, value + self.mapping.last_id)
                            #print(fk_table, self.fk_mapping.get(fk_table)) #FIXME
                    # if we're postprocessing an update we should restore the id as well
                    if key == 'id':
                        if table in self.fk_mapping:
                            value = int(value)
                            postprocessed_row[key] = self.fk_mapping[table].get(value, value)
                            if table == __debug: print(key, target_row[key], postprocessed_row[key]) #FIXME
                        else:
                            postprocessed_row[key] = value
                        if table == __debug: print(key, target_row[key], postprocessed_row[key]) #FIXME

                    if value and target_record in self.ref_mapping:  # manage __ref__
                        # first find the target table of the reference
                        value = int(value)
                        ref_column = self.ref_mapping[target_record]
                        ref_table = target_row[ref_column].replace('.', '_')
                        postprocessed_row[key] = self.fk_mapping.get(ref_table, {}).get(
                            value, value + self.mapping.last_id)
                #if table == __debug: print(key, target_row, postprocessed_row) #FIXME
                # don't write m2m lines if they exist in the target
                if 'id' not in postprocessed_row:
                    m2m_row = tuple([
                        str(postprocessed_row[x])
                        for x in sorted(postprocessed_row.keys())])
                    if m2m_row in m2m_rows or m2m_row in discriminations.get(table):
                        continue
                    m2m_rows.append(m2m_row)
                self.writers[table].writerow(postprocessed_row)
                #if table.startswith('note_'): print(target_row, postprocessed_row) #FIXME
            LOG.debug("Postprocessed %s: %d rows" % (table, counter))

    def update_one(self, filepath, connection):
        """ Apply updates in the target db with update file
        """
        table = basename(filepath).rsplit('.', 2)[0]
        has_data = False
        with open(filepath, 'rb') as update_csv:
            cursor = connection.cursor()
            reader = csv.DictReader(update_csv, delimiter=',')
            for update_row in reader:
                has_data = True
                items = [(k, v) for k, v in update_row.iteritems() if v != '']
                columns = ', '.join([i[0] for i in items])
                values = ', '.join(['%s' for i in items])
                args = [i[1] for i in items] + [update_row['id']]
                try:
                    cursor.execute('UPDATE %s SET (%s)=(%s) WHERE id=%s'
                                   % (table, columns, values, '%s'), tuple(args))
                    cursor.execute('RELEASE SAVEPOINT savepoint; SAVEPOINT savepoint')
                except Exception, e:
                    LOG.warn('Error updating table %s:\n%s', table, e.message)
                    cursor = connection.cursor()
                    cursor.execute('ROLLBACK TO savepoint')
                    cursor.close()
                    break
            if has_data:
                LOG.info(u'Successfully updated table %s', table)
            else:
                LOG.info(u'Nothing to update in table %s', table)
