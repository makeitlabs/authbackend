# vim:tabstop=2:shiftwidth=2:expandtab
from .templateCommon import *

from .accesslib import addQuickAccessQuery


def ubersearch(searchstr,only=None,membertypes=None):
  result = []
  if searchstr == "": return []

  if not only or 'members' in only:
    try:
      filter_expr = (
        Member.member.ilike('%'+searchstr+'%') |
        Member.nickname.ilike('%'+searchstr+'%') |
        Member.alt_email.ilike('%'+searchstr+'%') |
        Member.slack.ilike('%'+searchstr+'%') |
        Member.firstname.ilike('%'+searchstr+'%') |
        Member.plates.ilike('%'+searchstr+'%') |
        Member.lastname.ilike('%'+searchstr+'%') |
        Member.group.ilike('%'+searchstr+'%')
      )
      mq = Member.query.filter(filter_expr)
      mq = addQuickAccessQuery(mq)
      mq = mq.outerjoin(Subscription, Subscription.member_id == Member.id)
      rows = mq.all()
    except Exception as e:
      logger.warning(f"ubersearch member query failed with group: {e}, retrying without group filter")
      try:
        filter_expr = (
          Member.member.ilike('%'+searchstr+'%') |
          Member.nickname.ilike('%'+searchstr+'%') |
          Member.alt_email.ilike('%'+searchstr+'%') |
          Member.slack.ilike('%'+searchstr+'%') |
          Member.firstname.ilike('%'+searchstr+'%') |
          Member.plates.ilike('%'+searchstr+'%') |
          Member.lastname.ilike('%'+searchstr+'%')
        )
        mq = Member.query.filter(filter_expr)
        mq = addQuickAccessQuery(mq)
        mq = mq.outerjoin(Subscription, Subscription.member_id == Member.id)
        rows = mq.all()
      except Exception as e2:
        logger.error(f"ubersearch member query failed: {e2}")
        rows = []

    seen_members = set()
    for r in rows:
      (x, s) = r
      if x.id in seen_members: continue
      seen_members.add(x.id)
      if not membertypes or s in membertypes:
        is_inactive = ((s == "No Subscription") or (s == "Expired"))
        grp = getattr(x, 'group', None)
        grp = grp.strip() if (grp and grp.strip()) else ""
        has_group = bool(grp)
        if is_inactive:
          in_text = f"Inactive ({grp})" if has_group else "Inactive"
        else:
          in_text = grp if has_group else ""
        
        name_title = f"{x.firstname or ''} {x.lastname or ''}".strip()
        if not name_title:
          name_title = x.member or f"Member #{x.id}"

        result.append({
          'title': name_title,
          'in': in_text,
          'id': x.id,
          'member': x.member,
          'url': url_for("members.member_show", id=x.member)
        })

  if not only or 'resources' in only:
    try:
      for x in Resource.query.filter((Resource.name.ilike('%'+searchstr+'%') | Resource.description.ilike('%'+searchstr+'%'))).all():
        result.append({
          'title': "%s" % (x.name),
          'in': "Resource",
          'short': x.short,
          'id': x.id,
          'url': url_for("resources.resource_show", resource=x.name)
        })
    except Exception as e:
      logger.error(f"ubersearch resource query failed: {e}")

  if not only or 'tools' in only:
    try:
      for x in Tool.query.filter((Tool.name.ilike('%'+searchstr+'%'))).all():
        result.append({
          'title': "%s" % (x.name),
          'in': "Tool",
          'short': x.short,
          'id': x.id,
          'url': url_for("tools.tools_show", tool=x.id)
        })
    except Exception as e:
      logger.error(f"ubersearch tool query failed: {e}")

  if not only or 'nodes' in only:
    try:
      for x in Node.query.filter(Node.name.ilike('%'+searchstr+'%')).all():
        result.append({
          'title': "%s" % (x.name),
          'in': "Node",
          'id': x.id,
          'url': url_for("nodes.nodes_show", node=x.id)
        })
    except Exception as e:
      logger.error(f"ubersearch node query failed: {e}")

  return result
	

def cli_ubersearch(cmd,**kwargs):
	for x in  ubersearch(cmd[1]):
			print ("%s %s %s" %(x['title'],x['in'],x['url']))
