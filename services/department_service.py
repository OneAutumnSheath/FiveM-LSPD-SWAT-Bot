import discord
from discord.ext import commands
from typing import TYPE_CHECKING, Dict, List
from utils.decorators import log_on_completion

if TYPE_CHECKING:
    from main import MyBot

# Die Konfiguration kann hier oder in einer separaten config-Datei liegen
MULTI_SERVER_DEPARTMENT_ROLES: Dict[int, Dict[int, List[int]]] = {
    # ARMY
    1097625621875675188: {
        1134146376482181270: [1097834442283827290, 1108008526846103664, 1097832262302695464, 1348398323077480448, 1187804329646764104, 1097832273669267616, 1103356761630584892, 1124848353071603772, 1317317517928042506, 1332706191486488706, 1332706409439039558, 1317318324119666688, 1330348722625843302, 1125174538964058223, 1186008938144075847, 1332110439877972068, 1125174775380197416, 1219384062498570431, 1317318696368341052, 1401989491882983544, 1401989362455154738, 1317318837724516452, 1370038830660456478, 1376619013928648845, 1384953553067708497, 1367815114564173874],
        1134170231275782154: [1187756956425920645, 1187757319535206480, 1336018418389749771, 1136062113908019250, 1097653037968920776, 1197231640112549908, 1351261216991088831, 1352386268939419740, 1352386667503157422, 1352386756946825266, 1352386851788423238, 1287178400573947968, 1125174901989445693, 1269229762400878675, 1210891795563683922, 1339523576159666218, 1332705553142513774, 1332705938674815116, 1289716541658497055, 1343961616718233660, 1292864071967834133, 1238831879679901768, 1384953553067708497],
        1133474715311284315: [1097648080020574260, 1097625910242447422, 1097648131367248016, 1105121168383557742, 1228203847164497932, 1291908029947711531, 1223450533050847375, 1376613706116632837],
        1340823759904440441: [1143934031071817769, 1143934164924633118, 1395430402109214773, 1395430476310777938],
        1097653037968920776: [1125174901989445693, 1136062113908019250],
        1202304405748330568: [1274807277437845535, 1098684909155012718, 1196079090185277511, 1179837527398555738, 1251574089013924012, 1268203382146076756, 1284779950020366432, 1320443185251749961, 1333876088119754872, 1339688740532260901, 1351231108674748581, 1376340623019348158, 1381359568516284486, 1385331490891763782, 1385387268570615902]
    }
}

class DepartmentService(commands.Cog):
    def __init__(self, bot: "MyBot"):
        self.bot = bot
        self.__cog_name__ = "DepartmentService"

    async def _check_and_update_header_role(self, member: discord.Member, required_role_ids: List[int], header_role_id: int):
        """Private Helfer-Methode zur Überprüfung einer einzelnen Überschriften-Rolle."""
        header_role = member.guild.get_role(header_role_id)
        if not header_role: return

        has_required_role = any(role.id in required_role_ids for role in member.roles)
        has_header_role = header_role in member.roles

        try:
            if has_required_role and not has_header_role:
                await member.add_roles(header_role, reason="Automatische Zuweisung der Überschriften-Rolle")
            elif not has_required_role and has_header_role:
                await member.remove_roles(header_role, reason="Automatische Entfernung der Überschriften-Rolle")
        except discord.Forbidden:
            print(f"Keine Berechtigung, die Rolle '{header_role.name}' für {member.display_name} zu verwalten.")
        except discord.HTTPException:
            pass # Ignoriere andere HTTP-Fehler (z.B. User hat den Server verlassen)

    # --- Öffentliche API-Methoden ---
    
    async def check_all_departments_for_member(self, member: discord.Member):
        """Prüft alle konfigurierten Departments für ein einzelnes Mitglied."""
        department_roles_for_guild = MULTI_SERVER_DEPARTMENT_ROLES.get(member.guild.id)
        if not department_roles_for_guild:
            return

        for header_role_id, required_roles in department_roles_for_guild.items():
            await self._check_and_update_header_role(member, required_roles, header_role_id)

    # --- Event-Listener ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Reagiert automatisch auf Rollenänderungen."""
        if before.roles != after.roles:
            await self.check_all_departments_for_member(after)

async def setup(bot: "MyBot"):
    await bot.add_cog(DepartmentService(bot))