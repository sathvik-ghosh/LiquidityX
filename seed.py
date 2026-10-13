"""SYNTHETIC DEMO DATA - not real businesses. 14 companies, one demo crisis."""
from datetime import date, timedelta
from .db import audit, set_setting
from .money import lakh

AS_OF = date(2026, 10, 13)

COMPANIES = [  # name, type, opening cash (L), min cash (L)
    ("Apex Motors", "customer", 900, 100),
    ("Bharat Precision Components", "manufacturer", 14, 8),
    ("Sundaram Castings", "supplier", 6, 4),
    ("Chola Steel Traders", "distributor", 9, 5),
    ("Madras Alloy Works", "supplier", 20, 5),
    ("Kaveri Fasteners", "supplier", 7, 3),
    ("Orion Auto Electricals", "manufacturer", 25, 10),
    ("Vega Logistics", "service", 5, 2),
    ("Trident Wholesale", "distributor", 40, 10),
    ("Lotus Retail Auto", "customer", 60, 15),
    ("Surya Polymers", "supplier", 12, 5),
    ("Delta Tooling", "supplier", 4, 2),
    ("Nova Packaging", "supplier", 5, 2),
    ("Himalaya Rubber", "supplier", 18, 6),
]

# payer, payee, amount (L), due in N days from AS_OF, expected delay, criticality, alt available
INVOICES = [
    ("Apex Motors", "Bharat Precision Components", 30, 5, 0, 5, 0),
    ("Apex Motors", "Orion Auto Electricals", 15, 9, 0, 4, 0),
    ("Bharat Precision Components", "Sundaram Castings", 22, 8, 0, 5, 0),
    ("Bharat Precision Components", "Kaveri Fasteners", 6, 10, 0, 3, 1),
    ("Bharat Precision Components", "Vega Logistics", 2, 6, 0, 2, 1),
    ("Sundaram Castings", "Chola Steel Traders", 18, 12, 0, 5, 0),
    ("Sundaram Castings", "Delta Tooling", 3, 11, 0, 3, 1),
    ("Chola Steel Traders", "Madras Alloy Works", 20, 14, 0, 4, 0),
    ("Kaveri Fasteners", "Himalaya Rubber", 4, 13, 0, 2, 1),
    ("Orion Auto Electricals", "Surya Polymers", 8, 10, 0, 3, 1),
    ("Orion Auto Electricals", "Nova Packaging", 3, 12, 0, 2, 1),
    ("Trident Wholesale", "Bharat Precision Components", 10, 20, 0, 3, 1),
    ("Lotus Retail Auto", "Trident Wholesale", 25, 15, 0, 3, 1),
    ("Surya Polymers", "Himalaya Rubber", 3, 16, 0, 2, 1),
    ("Delta Tooling", "Madras Alloy Works", 2, 18, 0, 3, 0),
    ("Lotus Retail Auto", "Bharat Precision Components", 4, -10, 10, 3, 1),  # overdue
]

TXNS = [  # company, day offset, amount (L, signed), category, confirmed
    ("Bharat Precision Components", 7, -10, "payroll", 1),
    ("Bharat Precision Components", 37, -10, "payroll", 0),
    ("Sundaram Castings", 7, -5, "payroll", 1),
    ("Sundaram Castings", 3, 4, "other_sales", 0),
    ("Chola Steel Traders", 9, -3, "payroll", 1),
    ("Delta Tooling", 10, -1.5, "payroll", 1),
    ("Kaveri Fasteners", 8, -2, "payroll", 1),
    ("Orion Auto Electricals", 8, -12, "payroll", 1),
]


def seed_demo(conn):
    with conn:
        ids = {}
        for name, typ, cash, mn in COMPANIES:
            cur = conn.execute("INSERT INTO companies(name,type,opening_cash,min_cash,is_demo)"
                               " VALUES(?,?,?,?,1)", (name, typ, lakh(cash), lakh(mn)))
            ids[name] = cur.lastrowid
        for payer, payee, amt, due, delay, crit, alt in INVOICES:
            cur = conn.execute(
                "INSERT INTO relationships(payer_id,payee_id,kind,criticality,alternative_available)"
                " VALUES(?,?,?,?,?) ON CONFLICT(payer_id,payee_id) DO UPDATE SET kind=kind "
                "RETURNING id", (ids[payer], ids[payee], "trade_payment", crit, alt))
            rid = cur.fetchone()[0]
            conn.execute("INSERT INTO invoices(relationship_id,amount,due_date,expected_delay_days)"
                         " VALUES(?,?,?,?)",
                         (rid, lakh(amt), (AS_OF + timedelta(days=due)).isoformat(), delay))
        for co, off, amt, cat, conf in TXNS:
            conn.execute("INSERT INTO cash_transactions(company_id,txn_date,amount,category,confirmed)"
                         " VALUES(?,?,?,?,?)",
                         (ids[co], (AS_OF + timedelta(days=off)).isoformat(), lakh(amt), cat, conf))
    seed_inventory(conn, ids)
    audit(conn, "seed_demo", {"companies": len(COMPANIES), "synthetic": True})
    return ids


# company, sku, desc, category, qty, unit cost Rs, price Rs, location, bought days ago, last move days ago,
# monthly demand, lead time, critical, hold, reason, hold deadline (+days), expiry (+days), restricted
INVENTORY = [
 ("Bharat Precision Components","BPC-ST-100","Forged steel shaft 100mm","Shafts",1200,1800,2600,"Chennai-A",60,5,400,45,1,"none","",None,None,0),
 ("Bharat Precision Components","BPC-BR-220","Brass bushing 22mm","Bushings",5000,120,190,"Chennai-A",200,20,600,20,0,"none","",None,None,0),
 ("Bharat Precision Components","BPC-BR-220","Brass bushing 22mm","Bushings",300,120,190,"Pune-B",30,2,600,20,0,"none","",None,None,0),
 ("Bharat Precision Components","BPC-GR-310","Helical gear set","Gears",300,5500,8200,"Chennai-A",45,40,120,60,1,"quality","Hardness test failed on 2 of 20 samples; full inspection pending",9,None,0),
 ("Bharat Precision Components","BPC-GR-315","Gear set - Apex spec","Gears",180,5200,7600,"Chennai-A",220,140,0,60,0,"customer_specific","Built to Apex drawing 77-B; no other buyer identified",None,None,0),
 ("Bharat Precision Components","BPC-CS-400","Casing 400 series","Casings",220,4000,5800,"Chennai-B",90,60,0,30,0,"damaged","Transit damage to mounting lugs; repairable",None,None,0),
 ("Bharat Precision Components","BPC-OB-050","Legacy flange 50mm (discontinued)","Flanges",2500,340,500,"Chennai-B",600,400,0,30,0,"obsolete","Product line discontinued",None,None,0),
 ("Bharat Precision Components","BPC-FS-120","Spring washer pack","Fasteners",9000,14,24,"Chennai-A",150,12,1000,15,0,"none","",None,None,0),
 ("Bharat Precision Components","BPC-RB-070","Rubber seal kit","Seals",3000,90,150,"Chennai-B",420,200,0,20,0,"expired","Shelf-life expired",None,-30,1),
 ("Bharat Precision Components","BPC-CT-900","Coated shaft","Shafts",400,2400,3500,"Chennai-A",70,50,0,40,0,"certification","Coating certificate lapsed; re-certification required",20,None,0),
 ("Bharat Precision Components","BPC-PL-330","Plate 3mm","Plates",800,650,900,"Chennai-B",110,75,0,25,0,"cancelled_order","Customer cancelled PO-8841",None,None,0),
 ("Bharat Precision Components","BPC-WS-010","Weld stock","Raw material",600,1100,1500,"Chennai-B",95,80,0,25,0,"supplier_dispute","Supplier disputes quantity invoiced",None,None,0),
 ("Bharat Precision Components","BPC-DC-005","Imported controller board","Electronics",120,7000,10500,"Chennai-A",35,30,10,90,1,"missing_docs","Customs/bill-of-entry paperwork missing",None,None,0),
 ("Bharat Precision Components","BPC-SC-001","Cast housing (cracked)","Casings",300,2000,3000,"Chennai-B",160,150,0,30,0,"damaged","Cracks found; unsafe for use or sale",None,None,1),
 ("Bharat Precision Components","BPC-AX-777","Axle assembly","Assemblies",90,9000,13500,"Chennai-A",25,25,30,50,0,"customer_order","Held for Apex PO-9120; release date unconfirmed",12,None,0),
 ("Sundaram Castings","SC-BL-010","Casting blanks","Castings",4000,300,420,"Chennai-C",120,30,500,25,0,"none","",None,None,0),
 ("Orion Auto Electricals","OAE-RL-33","Relay modules","Electronics",2500,260,380,"Chennai-D",300,150,100,30,0,"none","",None,None,0),
]


def seed_inventory(conn, ids):
    with conn:
        for (co, sku, desc, cat, qty, uc, sp, loc, bought, moved, dem, lead, crit, hold, why,
             dl, exp, restr) in INVENTORY:
            d = lambda n: None if n is None else (AS_OF + timedelta(days=n)).isoformat()
            conn.execute("""INSERT INTO inventory_batches(company_id,sku,description,category,qty,
              unit_cost,selling_price,location,purchase_date,last_move_date,monthly_demand,
              lead_time_days,critical,hold_status,hold_reason,hold_deadline,expiry_date,restricted)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (ids[co], sku, desc, cat, qty, uc * 100, sp * 100, loc, d(-bought), d(-moved), dem, lead,
               crit, hold, why, d(dl), d(exp), restr))
    set_setting(conn, "as_of", AS_OF.isoformat())
