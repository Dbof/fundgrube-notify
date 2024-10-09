# Fundgrube Notify
Scans the Fundgrube of [Media Markt](https://www.mediamarkt.de/de/data/fundgrube) and [Saturn](https://www.saturn.de/de/data/fundgrube) for items and send email notifications.

## Configuration
Check and edit the ``sample_products.json`` file. Add your search terms and max price for the items.

Rename ``sample.env`` to ``.env`` and edit it to set the SMTP email settings. Tested with GMail and an "app password".

The script creates the file ``old_results.csv`` while running, which saves all found results, so it does not notify on old entries. You can delete it if you want to have older results.

Also, install all requirements with:

```
pip3 install -r requirements.txt
```

## Run
```bash
python3 fundgrube.py --verbose sample_products.json
```
