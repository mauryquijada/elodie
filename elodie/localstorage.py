"""
Methods for interacting with information Elodie caches about stored media.
"""
from builtins import map
from builtins import object

import hashlib
import imagehash
import json
import os
import pickle
import sys

from math import radians, cos, sqrt
from shutil import copyfile
from PIL import Image
from time import strftime

from elodie import constants


class Db(object):

    """A class for interacting with the JSON files created by Elodie."""

    def __init__(self):
        # verify that the application directory (~/.elodie) exists,
        #   else create it
        if not os.path.exists(constants.application_directory):
            os.makedirs(constants.application_directory)

        # If the hash db doesn't exist we create it.
        # Otherwise we only open for reading
        if not os.path.isfile(constants.hash_db):
            with open(constants.hash_db, 'a'):
                os.utime(constants.hash_db, None)

        self.hash_db = {}

        # We know from above that this file exists so we open it
        #   for reading only.
        with open(constants.hash_db, 'r') as f:
            try:
                self.hash_db = json.load(f)
            except ValueError:
                pass

        # If the location db doesn't exist we create it.
        # Otherwise we only open for reading
        if not os.path.isfile(constants.location_db):
            with open(constants.location_db, 'a'):
                os.utime(constants.location_db, None)

        self.location_db = []

        # We know from above that this file exists so we open it
        #   for reading only.
        with open(constants.location_db, 'r') as f:
            try:
                self.location_db = json.load(f)
            except ValueError:
                pass

        # If the phash db doesn't exist we create it.
        # Otherwise we only open for reading
        if not os.path.isfile(constants.phash_db):
            with open(constants.phash_db, 'a'):
                os.utime(constants.phash_db, None)

        self.phash_db = {}

        # We know from above that this file exists so we open it
        #   for reading only.
        if not os.path.getsize(constants.phash_db) == 0:  # Only unpickle if file isn't empty.
            with open(constants.phash_db, 'rb') as f:
                self.phash_db = pickle.load(f)

    def add_phash(self, key, value, write=False):
        """Add a phash to the phash db.

        :param str key:
        :param str value:
        :param bool write: If true, write the hash db to disk.
        """
        self.phash_db[key] = value
        if(write is True):
            self.update_hash_db()

    def add_hash(self, key, value, write=False):
        """Add a hash to the hash db.

        :param str key:
        :param str value:
        :param bool write: If true, write the hash db to disk.
        """
        self.hash_db[key] = value
        if(write is True):
            self.update_hash_db()

    # Location database
    # Currently quite simple just a list of long/lat pairs with a name
    # If it gets many entries a lookup might take too long and a better
    # structure might be needed. Some speed up ideas:
    # - Sort it and inter-half method can be used
    # - Use integer part of long or lat as key to get a lower search list
    # - Cache a small number of lookups, photos are likely to be taken in
    #   clusters around a spot during import.
    def add_location(self, latitude, longitude, place, write=False):
        """Add a location to the database.

        :param float latitude: Latitude of the location.
        :param float longitude: Longitude of the location.
        :param str place: Name for the location.
        :param bool write: If true, write the location db to disk.
        """
        data = {}
        data['lat'] = latitude
        data['long'] = longitude
        data['name'] = place
        self.location_db.append(data)
        if(write is True):
            self.update_location_db()

    def backup_hash_db(self):
        """Backs up the hash db."""
        if os.path.isfile(constants.hash_db):
            mask = strftime('%Y-%m-%d_%H-%M-%S')
            hash_backup_file_name = '%s-%s' % (constants.hash_db, mask)
            copyfile(constants.hash_db, hash_backup_file_name)

        if os.path.isfile(constants.phash_db):
            mask = strftime('%Y-%m-%d_%H-%M-%S')
            phash_backup_file_name = '%s-%s' % (constants.phash_db, mask)
            copyfile(constants.phash_db, phash_backup_file_name)
            
        return hash_backup_file_name

    def check_hash(self, key):
        """Check whether a hash is present for the given key.

        :param str key:
        :returns: bool
        """
        return key in self.hash_db

    def check_phash(self, key):
        """Check whether a phash is present for the given key.

        :param str key:
        :returns: bool
        """
        return key in self.phash_db

    def checksum(self, file_path, blocksize=65536):
        """Create a hash value for the given file.

        See http://stackoverflow.com/a/3431835/1318758.

        :param str file_path: Path to the file to create a hash for.
        :param int blocksize: Read blocks of this size from the file when
            creating the hash.
        :returns: str or None
        """
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            buf = f.read(blocksize)

            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(blocksize)
            return hasher.hexdigest()
        return None

    def phash(self, file_path):
        """Create a phash value for the given file.

        :param str file_path: Path to the file to create a hash for.
        :returns: str or None
        """
        with open(file_path, 'rb') as f, Image.open(f) as img:
            img_hash = imagehash.phash(img, hash_size=constants.hash_size)
            return img_hash    
        

    def get_hash(self, key):
        """Get the hash value for a given key.

        :param str key:
        :returns: str or None
        """
        if(self.check_hash(key) is True):
            return self.hash_db[key]
        return None

    def get_phash(self, key):
        """Get the phash value for a given key.

        :param str key:
        :returns: str or None
        """
        if(self.check_phash(key) is True):
            return self.phash_db[key]
        return None

    def get_location_name(self, latitude, longitude, threshold_m):
        """Find a name for a location in the database.

        :param float latitude: Latitude of the location.
        :param float longitude: Longitude of the location.
        :param int threshold_m: Location in the database must be this close to
            the given latitude and longitude.
        :returns: str, or None if a matching location couldn't be found.
        """
        last_d = sys.maxsize
        name = None
        for data in self.location_db:
            # As threshold is quite small use simple math
            # From http://stackoverflow.com/questions/15736995/how-can-i-quickly-estimate-the-distance-between-two-latitude-longitude-points  # noqa
            # convert decimal degrees to radians

            lon1, lat1, lon2, lat2 = list(map(
                radians,
                [longitude, latitude, data['long'], data['lat']]
            ))

            r = 6371000  # radius of the earth in m
            x = (lon2 - lon1) * cos(0.5 * (lat2 + lat1))
            y = lat2 - lat1
            d = r * sqrt(x * x + y * y)
            # Use if closer then threshold_km reuse lookup
            if(d <= threshold_m and d < last_d):
                name = data['name']
            last_d = d

        return name

    def get_location_coordinates(self, name):
        """Get the latitude and longitude for a location.

        :param str name: Name of the location.
        :returns: tuple(float), or None if the location wasn't in the database.
        """
        for data in self.location_db:
            if data['name'] == name:
                return (data['lat'], data['long'])

        return None

    def all(self):
        """Generator to get all entries from self.hash_db

        :returns tuple(string)
        """
        for checksum, path in self.hash_db.items():
            yield (checksum, path)

    def reset_hash_db(self):
        self.hash_db = {}
        self.phash_db = {}

    def update_hash_db(self):
        """Write the hash db to disk."""
        with open(constants.hash_db, 'w') as f:
            json.dump(self.hash_db, f)

        with open(constants.phash_db, 'wb') as f:
            pickle.dump(self.phash_db, f)

    def update_location_db(self):
        """Write the location db to disk."""
        with open(constants.location_db, 'w') as f:
            json.dump(self.location_db, f)