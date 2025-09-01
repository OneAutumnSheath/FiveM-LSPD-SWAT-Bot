# config/role_sync_mapping.py

# Hier definierst du die 1-zu-1-Übersetzung der Rollen.
ROLE_SYNC_MAPPING = {
    # Key: ID des Quell-Servers, auf dem die Änderung passiert
    1097625621875675188: {
        # Die ID des Ziel-Servers, auf den die Änderung übertragen wird
        "target_guild_id": 1363986017907900428,
        # Das eigentliche Mapping der Rollen
        "roles": {
            # Key: ID der Rolle auf dem Quell-Server
            # Value: ID der entsprechenden Rolle auf dem Ziel-Server
            1384953553067708497: 1397406305681014844,  # Admiral
            1125174538964058223: 1397406249733062790,  # Commander
            1186008938144075847: 1397406172335706243, # Co-Commander
            1368937338989969458: 1397404541829517434, # Instructor
            1351261216991088831: 1397404485193826355, # Operator
            1287178400573947968: 1397404399835287632, # Trainee
            1351231108674748581: 1363986177169817693, # FIB
            1385331490891763782: 1397410961408786618, # LSPD
        }
    }
}