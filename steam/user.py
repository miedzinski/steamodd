"""
Module for reading Steam user account data

Copyright (c) 2010, Anthony Garcia <lagg@lavabit.com>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import json, urllib2, steam, time, os, sqlite3
import cPickle as pickle

class ProfileError(Exception):
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg

    def __str__(self):
        return repr(self.msg)

class profile:
    """ Functions for reading user account data """

    def _get_id64_cache_path(self):
        return os.path.join(steam.get_cache_dir(), "id64_cache.db")

    def _create_id64_db(self):
        _id64_cache_conn = sqlite3.connect(self._get_id64_cache_path())
        _id64_cache = _id64_cache_conn.cursor()
        _id64_cache.execute("CREATE TABLE IF NOT EXISTS cache (sid TEXT, id64 INTEGER PRIMARY KEY)")
        _id64_cache_conn.commit()
        _id64_cache.close()

    # Hopefully Valve will provide a request for doing this so we won't
    # have to use the old API
    def get_id64_from_sid(self, sid):
        """ This uses the old API, caches
        64 bit ID mappings in id64_cache* """

        if sid.isdigit(): return sid

        conn = sqlite3.connect(self._get_id64_cache_path())
        cache = conn.cursor()
        ids = cache.execute("SELECT id64 FROM cache WHERE sid=?", (sid,)).fetchone()
        if ids:
            cache.close()
            return ids[0]

        prof = urllib2.urlopen(self._old_profile_url.format(sid)).read()

        if type(sid) == str and prof.find("<steamID64>") != -1:
            prof = (prof[prof.find("<steamID64>")+11:
                             prof.find("</steamID64>")])
            cache.execute("INSERT OR IGNORE INTO cache (id64) VALUES (?)",
                          (prof,))
            cache.execute("UPDATE cache SET sid=? WHERE id64=?", (sid, prof,))
            conn.commit()
            cache.close()

            return prof

    def get_summary(self, sid):
        """ Returns the summary object. The wrapper functions should
        normally be used instead."""
        id64 = self.get_id64_from_sid(str(sid).encode("ascii", "replace"))

        if not id64:
            #Assume it's the 64 bit ID
            id64 = sid

        self._summary_object = (json.loads(urllib2.urlopen(self._profile_url + str(id64)).read().encode("utf-8"))
                               ["response"]["players"]["player"][0])

        if not self._summary_object:
            raise ProfileError("Profile not found")

        return self._summary_object

    def load_summary_file(self, summary, pickled = True):
        """ Loads a profile summary object from the given file
        object. If pickled == True assume it's a pickled dict, otherwise
        a JSON object. """

        if pickled:
            self._summary_object = pickle.load(summary)
        else:
            self._summary_object = json.load(summary)

    def get_summary_object(self):
        try:
            return self._summary_object
        except AttributeError:
            raise ProfileError("No summary")

    def get_id64(self):
        """ Returns the 64 bit steam ID (use with other API requests) """
        return self._summary_object["steamid"]

    def get_persona(self):
        """ Returns the user's persona (what you usually see in-game) """
        return self._summary_object["personaname"]

    def get_profile_url(self):
        """ Returns a URL to the user's Community profile page """
        return self._summary_object["profileurl"]

    def get_avatar_url(self, size):
        """ Returns a URL to the user's avatar, see AVATAR_* """
        return self._summary_object[size]

    def get_status(self):
        """ Returns the user's status as a string. (or integer if unrecognized)"""
        status = self._summary_object["personastate"]

        if status == 0:   return "offline"
        elif status == 1: return "online"
        elif status == 2: return "busy"
        elif status == 3: return "away"
        elif status == 4: return "snooze"

        return status

    def get_visibility(self):
        """ Returns the visibility setting of the profile """
        vis = self._summary_object["communityvisibilitystate"]

        if vis == 1: return "private"
        if vis == 2: return "friends"
        if vis == 3: return "public"

        return vis

    # This might be redundant, can we still get an id64 from an unconfigured profile?
    def is_configured(self):
        """ Returns true if the user has created a Community profile """

        return self._summary_object.get("profilestate", False)

    def get_last_online(self):
        """ Returns the last time the user was online as a localtime
        time.struct_time struct """

        return time.localtime(self._summary_object["lastlogoff"])

    def is_comment_enabled(self):
        """ Returns true if the profile allows public comments """

        return self._summary_object.get("commentpermission", False)

    def get_real_name(self):
        """ Returns the user's real name if it's set and public """

        return self._summary_object.get("realname")

    # This isn't very useful yet since there's no API request
    # for groups yet, and I'm avoiding using the old API
    # as much as possible
    def get_primary_group(self):
        """ Returns the user's primary group ID if set. """

        return self._summary_object.get("primaryclanid")

    def get_creation_date(self):
        """ Returns the account creation date as a localtime time.struct_time
        struct if public"""

        timestamp = self._summary_object.get("timecreated")
        if timestamp:
            return time.localtime(timestamp)

    def get_current_game(self):
        """ Returns a dict of game info if the user is playing if public and set
        id is an integer if it's a steam game
        server is the IP address:port string if they're on a server
        extra is the game name """
        ret = {}
        if self.get_visibility() == "public":
            if "gameid" in self._summary_object:
                ret["id"] = self._summary_object["gameid"]
            if "gameserverip" in self._summary_object:
                ret["server"] = self._summary_object["gameserverip"]
            if "gameextrainfo" in self._summary_object:
                ret["extra"] = self._summary_object["gameextrainfo"]

            return ret

    def get_location(self):
        """ Returns a dict of location data if public and set
        country: A two char ISO country code
        state: A two char ISO state code """
        ret = {}
        if self.get_visibility() == "public":
            if "loccountrycode" in self._summary_object:
                ret["country"] = self._summary_object["loccountrycode"]
            if "locstatecode" in self._summary_object:
                ret["state"] = self._summary_object["locstatecode"]

            return ret

    def __init__(self, sid = None):
        """ Creates a profile instance for the given user """
        self._old_profile_url = "http://steamcommunity.com/id/{0:s}?xml=1"
        self._profile_url = ("http://api.steampowered.com/ISteamUser/GetPlayerSummaries/"
                             "v0001/?key=" + steam.get_api_key() + "&steamids=")
        self._create_id64_db()

        if sid:
            self.get_summary(sid)

    AVATAR_SMALL = "avatar"
    AVATAR_MEDIUM = "avatarmedium"
    AVATAR_LARGE = "avatarfull"
