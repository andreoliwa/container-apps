# Mayan EDMS

- GitLab: https://gitlab.com/mayan-edms/mayan-edms
- Docs: https://docs.mayan-edms.com
- PDF: https://docs.mayan-edms.com/pdf/mayan/latest/mayan.pdf

# Setup

- [Quick setup with Docker Compose](https://docs.mayan-edms.com/topics/docker.html#using-docker-compose)
- Add sources: menu _System / Setup / Sources_
  - Staging, folder `/srv/staging`, preview width 200
  - Watch, folder `/srv/watch`
- Add cabinets inside cabinets, on a tree structure that can mimic a directory tree
- Add tags
- [Upgrading](https://docs.mayan-edms.com/topics/docker.html#upgrading)

# Troubleshooting

## IndexInstanceNode matching query does not exist

> mayan-app | mayan.apps.document_indexing.models.IndexInstanceNode.DoesNotExist: IndexInstanceNode matching query does not exist.

Fix the model attributes on the index: [Contents for index: Creation date :: WAA Mayan](http://mayan:8001/#/indexing/instances/nodes/18460/)

But the error might still persist:

- [IndexInstanceNode matching query does not exist - Mayan EDMS community forum](https://forum.mayan-edms.com/viewtopic.php?t=5872)
- [Batch metadata processing or parsing will fail the index tasks: IndexInstanceNode matching query does not exist. (#720) · Issues · Mayan EDMS / Mayan EDMS · GitLab](https://gitlab.com/mayan-edms/mayan-edms/-/issues/720)

## Search not working

Restore the Django search backend and ditch Whoosh.

- [Cannot search keyword in PDF document - Mayan EDMS community forum](https://forum.mayan-edms.com/viewtopic.php?t=5673)
- [Search — Mayan EDMS 4.2.1 documentation](https://docs.mayan-edms.com/chapters/search.html)
