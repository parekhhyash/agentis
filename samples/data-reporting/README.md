# Sample data for the Data & Reporting agent

Made-up data for **Chai & Crumbs**, a small Indian snacks and sweets brand that sells on its website, Amazon, Flipkart, Instagram and one shop. It covers 1 April to 11 October 2026. Every name and number is invented.

| File | Rows | What's in it |
|---|---|---|
| `sales_orders.csv` | 2,631 | One row per order: date (DD/MM/YYYY), customer, city, state, channel, product, category, quantity, unit price, discount, order total (₹), payment method, status (Delivered, Shipped, Returned, Cancelled), repeat customer (Yes/No) |
| `expenses.csv` | 140 | Every payment: date, category (Salaries, Rent, Ads - Meta, Ads - Google, Packaging, Shipping, Marketing, Software, Utilities), vendor, amount (₹), paid by, GST included |
| `marketing_campaigns.xlsx` | 14 | One row per campaign: channel, start and end dates, spend, impressions, clicks, leads, orders, revenue, ROAS |
| `inventory.csv` | 12 | One row per product: SKU, category, stock on hand, reorder level, unit cost (₹), supplier, last restocked |

## How to use them

1. In Agentis, click the **paperclip** in the message box and pick a file. You can also upload it once under **Connect > Data files** and attach it from there later.
2. Ask a question about the attached file. The Manager hands anything about numbers to Data & Reporting, or you can pick Data & Reporting yourself.
3. To try Google Sheets, open a file in Google Sheets (File > Import), then add the sheet's link under **Connect > Data files > Add a Google Sheet**.

Things to know when testing:
- **One file per chart.** Each chart or number comes from one file; Data & Reporting doesn't join two files. Ask about orders and expenses separately.
- **Relative dates.** "Last month" and "the last 30 days" count back from the day you ask. These answers assume you ask on **12 October 2026**, so last month is September.
- **What counts as revenue.** If you just say "revenue", the agent may include returned and cancelled orders. Say "delivered and shipped orders" to match the numbers below.

## Prompts to try, and the answers to expect

### Sales (`sales_orders.csv`)

| Ask | You should see |
|---|---|
| What was my revenue last month from delivered and shipped orders? | **₹3,44,109** in September (500 orders placed that month; ₹3,93,324 if returns and cancellations are counted) |
| Show monthly revenue from delivered and shipped orders as a chart | Growth from **₹1,06,619** (April) to **₹3,44,109** (September); October has **₹2,05,463** in its first 11 days |
| Which sales channel brings in the most revenue? | **Website ₹4,27,985**, then Amazon ₹3,27,713, Instagram Shop ₹1,89,056, Flipkart ₹1,85,468, Offline store ₹1,77,710 (delivered and shipped) |
| What are my top 5 products by revenue? | **Dry Fruit Laddoo Box ₹2,18,754**, Kaju Katli 250g ₹1,84,613, Festive Hamper Large ₹1,53,816, Kashmiri Kahwa 100g ₹1,43,147, Assam Masala Chai 250g ₹1,12,065 |
| What's the return rate for each payment method? | **COD 11.9%**, about four times UPI (3.0%), Card (2.7%) and NetBanking (2.5%) |
| How many COD orders were returned in the last 30 days? | **16** (orders placed from 12 September) |
| What share of orders come from repeat customers each month? | Rising from **13%** in April to **36%** in October |
| Which cities order the most? | **Mumbai 390**, Bengaluru 355, Delhi 293, Hyderabad 221, Pune 220 (delivered and shipped orders) |
| Break down last month's revenue by category | **Gift Boxes ₹1,73,110**, Sweets ₹83,815, Beverages ₹53,439, Snacks ₹33,745 |
| What's my average order value? | **₹540** across 2,421 delivered and shipped orders |

### Expenses (`expenses.csv`)

| Ask | You should see |
|---|---|
| What did I spend last month? | **₹3,71,782** in September |
| Where does my money go? Show spending by category | **Salaries ₹9,45,000**, Ads - Meta ₹3,19,006, Rent ₹2,45,000, Shipping ₹2,16,589, Ads - Google ₹2,00,605, Packaging ₹1,50,484, Marketing ₹1,25,000, Software ₹81,900, Utilities ₹76,698 |
| Compare Meta and Google ad spend by month | Meta is higher every month; both rise in September for the festive season (₹96,830 on ads that month) |

### Campaigns (`marketing_campaigns.xlsx`)

| Ask | You should see |
|---|---|
| Which campaigns had the best and worst ROAS? | Best: **Festive WhatsApp Broadcast 20.59**, Rakhi Gift Boxes 4.33. Worst: **Back to Office Snacks (LinkedIn) 0.10**, Rakhi Influencers 0.36, Diwali Influencers 0.49 |
| Show spend and revenue by channel | Amazon Ads has the most spend (₹1,52,529) and revenue (₹3,83,233); Influencers and LinkedIn Ads spent more than they brought in |
| How much did all campaigns spend, and what revenue did they bring? | **₹5,21,174** spent, **₹9,50,866** revenue |

### Stock (`inventory.csv`)

| Ask | You should see |
|---|---|
| Which products have fewer than 50 units in stock? | **Kashmiri Kahwa 100g (18)**, Festive Hamper Large (35), Assam Masala Chai 250g (44), Filter Coffee Powder 250g (44) |

## Beyond one file

- **Your Agentis activity** (no file needed): "How many leads did Agentis find this month, and how many of my emails got replies?"
- **Several agents in one message** (Manager): attach `sales_orders.csv` and ask "Report last month's revenue by channel and write a LinkedIn post about our best channel".
- **On a schedule** (Operations): link the orders sheet from Google Sheets, then ask "Every Monday at 9, report last week's revenue by channel and email it to me".

## Making the files again

The files come from `make_samples.py`, which is seeded so it always produces the same data. It needs `openpyxl`, which is already in the backend's environment:

```bash
backend/.venv/bin/python samples/data-reporting/make_samples.py samples/data-reporting
```
