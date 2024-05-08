import json
import os
from openai import AzureOpenAI
from urllib.parse import quote
from promptflow.core import tool
from promptflow.contracts.multimedia import Image
from promptflow.tracing import trace
import sqlite3
import pandas as pd

MAX_ITER = 20
global client

import json

system_message = """
### SQLite table with properties:
    #
    #  Number_of_Orders INTEGER "the number of orders processed"
    #  Sum_of_Order_Value_USD REAL "the total value of the orders processed in USD"
    #  Sum_of_Number_of_Items REAL "the sum of items in the orders processed"
    #  Number_of_Orders_with_Discount INTEGER "the number of orders that received a discount"
    #  Sum_of_Discount_Percentage REAL "the sum of discount percentage -- useful to calculate average discounts given"
    #  Sum_of_Shipping_Cost_USD REAL "the sum of shipping cost for the processed orders"
    #  Number_of_Orders_Returned INTEGER "the number of orders returned by the customers"
    #  Number_of_Orders_Cancelled INTEGER "the number or orders cancelled by the customers before they were sent out"
    #  Sum_of_Time_to_Fulfillment REAL "the sum of time to fulfillment"
    #  Number_of_Orders_Repeat_Customers INTEGER "number of orders that were placed by repeat customers"
    #  Year INTEGER
    #  Month INTEGER
    #  Day INTEGER
    #  Date TIMESTAMP
    #  Day_of_Week INTEGER in 0 based format, Monday is 0, Tuesday is 1, etc.
    #  main_category TEXT
    #  sub_category TEXT
    #  product_type TEXT
    #  Region TEXT
    #
In this table all numbers are already aggregated, so all queries will be some type of aggregation with group by.
for instance when asked:

Query the number of orders grouped by Month

    SELECT SUM(Number_of_Orders), 
           Month
    FROM order_data GROUP BY Month

query to get the sum of number of orders, sum of order value, average order value, average shipping cost by month

    SELECT SUM(Number_of_Orders), 
           SUM(Sum_of_Order_Value),
           SUM(Sum_of_Order_Value)/SUM(Number_of_Orders) as Avg_Order_Value,
           SUM(Sum_of_Shipping_Cost)/SUM(Number_of_Orders) as Avg_Shipping_Cost, 
           Month
    FROM order_data GROUP BY Month

whenever you get an average, make sure to use the SUM of the values divided by the SUM of the counts to get the correct average. 
The way the data is structured, you cannot use AVG() function in SQL. 

        SUM(Sum_of_Order_Value)/SUM(Number_of_Orders) as Avg_Order_Value

When asked to list categories, days, or other entities, make sure to always query with DISTICT, for instance: 
Query for all the values for the main_category

    SELECT DISTINCT main_category
    FROM order_data

Query for all the days of the week in January where the number of orders is greater than 10

    SELECT DISTINCT Day_of_Week
    FROM order_data
    WHERE Month = 1 AND Number_of_Orders > 10

If you are aked for ratios, make sure to calculate the ratio by dividing the two values and multiplying by 1.0 to force a float division. 
For instance, to get the return rate by month, you can use the following query:

    SELECT SUM(Number_of_Orders_Returned) * 1.0 / SUM(Number_of_Orders)
    FROM order_data
        
query for all the days in January 2023 where the number of orders is greater than 700

    SELECT Day, SUM(Number_of_Orders) as Total_Orders
    FROM order_data
    WHERE Month = 1 AND Year = 2023
    GROUP BY Day
    HAVING SUM(Number_of_Orders) > 700

in your reply only provide the query with no extra formatting
never use the AVG() function in SQL, always use SUM() / SUM() to get the average

Note that all categories, i.e. main_category, sub_category, product_type and Region all contain only UPPER CASE values. 
So, whenever you are filtering or grouping by these values, make sure to provide the values in UPPER CASE.

Here are the valid values for the main_category, sub_category, product_type -- note that these are hiearchical:
[{"main_category":"APPAREL","sub_category":"MEN'S CLOTHING","product_type":"JACKETS & VESTS"},{"main_category":"APPAREL","sub_category":"MEN'S CLOTHING","product_type":"SHIRTS"},{"main_category":"APPAREL","sub_category":"MEN'S CLOTHING","product_type":"PANTS & SHORTS"},{"main_category":"APPAREL","sub_category":"MEN'S CLOTHING","product_type":"UNDERWEAR & BASE LAYERS"},{"main_category":"APPAREL","sub_category":"MEN'S CLOTHING","product_type":"OTHER"},{"main_category":"APPAREL","sub_category":"WOMEN'S CLOTHING","product_type":"JACKETS & VESTS"},{"main_category":"APPAREL","sub_category":"WOMEN'S CLOTHING","product_type":"TOPS"},{"main_category":"APPAREL","sub_category":"WOMEN'S CLOTHING","product_type":"PANTS & SHORTS"},{"main_category":"APPAREL","sub_category":"WOMEN'S CLOTHING","product_type":"UNDERWEAR & BASE LAYERS"},{"main_category":"APPAREL","sub_category":"WOMEN'S CLOTHING","product_type":"OTHER"},{"main_category":"APPAREL","sub_category":"CHILDREN'S CLOTHING","product_type":"JACKETS & VESTS"},{"main_category":"APPAREL","sub_category":"CHILDREN'S CLOTHING","product_type":"TOPS"},{"main_category":"APPAREL","sub_category":"CHILDREN'S CLOTHING","product_type":"PANTS & SHORTS"},{"main_category":"APPAREL","sub_category":"CHILDREN'S CLOTHING","product_type":"UNDERWEAR & BASE LAYERS"},{"main_category":"APPAREL","sub_category":"CHILDREN'S CLOTHING","product_type":"OTHER"},{"main_category":"APPAREL","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"FOOTWEAR","sub_category":"MEN'S FOOTWEAR","product_type":"HIKING BOOTS"},{"main_category":"FOOTWEAR","sub_category":"MEN'S FOOTWEAR","product_type":"TRAIL SHOES"},{"main_category":"FOOTWEAR","sub_category":"MEN'S FOOTWEAR","product_type":"SANDALS"},{"main_category":"FOOTWEAR","sub_category":"MEN'S FOOTWEAR","product_type":"WINTER BOOTS"},{"main_category":"FOOTWEAR","sub_category":"MEN'S FOOTWEAR","product_type":"OTHER"},{"main_category":"FOOTWEAR","sub_category":"WOMEN'S FOOTWEAR","product_type":"HIKING BOOTS"},{"main_category":"FOOTWEAR","sub_category":"WOMEN'S FOOTWEAR","product_type":"TRAIL SHOES"},{"main_category":"FOOTWEAR","sub_category":"WOMEN'S FOOTWEAR","product_type":"SANDALS"},{"main_category":"FOOTWEAR","sub_category":"WOMEN'S FOOTWEAR","product_type":"WINTER BOOTS"},{"main_category":"FOOTWEAR","sub_category":"WOMEN'S FOOTWEAR","product_type":"OTHER"},{"main_category":"FOOTWEAR","sub_category":"CHILDREN'S FOOTWEAR","product_type":"HIKING BOOTS"},{"main_category":"FOOTWEAR","sub_category":"CHILDREN'S FOOTWEAR","product_type":"TRAIL SHOES"},{"main_category":"FOOTWEAR","sub_category":"CHILDREN'S FOOTWEAR","product_type":"SANDALS"},{"main_category":"FOOTWEAR","sub_category":"CHILDREN'S FOOTWEAR","product_type":"WINTER BOOTS"},{"main_category":"FOOTWEAR","sub_category":"CHILDREN'S FOOTWEAR","product_type":"OTHER"},{"main_category":"FOOTWEAR","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"CAMPING & HIKING","sub_category":"TENTS & SHELTERS","product_type":"BACKPACKING TENTS"},{"main_category":"CAMPING & HIKING","sub_category":"TENTS & SHELTERS","product_type":"FAMILY CAMPING TENTS"},{"main_category":"CAMPING & HIKING","sub_category":"TENTS & SHELTERS","product_type":"SHELTERS & TARPS"},{"main_category":"CAMPING & HIKING","sub_category":"TENTS & SHELTERS","product_type":"BIVYS"},{"main_category":"CAMPING & HIKING","sub_category":"TENTS & SHELTERS","product_type":"OTHER"},{"main_category":"CAMPING & HIKING","sub_category":"SLEEPING GEAR","product_type":"SLEEPING BAGS"},{"main_category":"CAMPING & HIKING","sub_category":"SLEEPING GEAR","product_type":"SLEEPING PADS"},{"main_category":"CAMPING & HIKING","sub_category":"SLEEPING GEAR","product_type":"HAMMOCKS"},{"main_category":"CAMPING & HIKING","sub_category":"SLEEPING GEAR","product_type":"LINERS"},{"main_category":"CAMPING & HIKING","sub_category":"SLEEPING GEAR","product_type":"OTHER"},{"main_category":"CAMPING & HIKING","sub_category":"BACKPACKS","product_type":"DAYPACKS"},{"main_category":"CAMPING & HIKING","sub_category":"BACKPACKS","product_type":"OVERNIGHT PACKS"},{"main_category":"CAMPING & HIKING","sub_category":"BACKPACKS","product_type":"EXTENDED TRIP PACKS"},{"main_category":"CAMPING & HIKING","sub_category":"BACKPACKS","product_type":"HYDRATION PACKS"},{"main_category":"CAMPING & HIKING","sub_category":"BACKPACKS","product_type":"OTHER"},{"main_category":"CAMPING & HIKING","sub_category":"COOKING GEAR","product_type":"STOVES"},{"main_category":"CAMPING & HIKING","sub_category":"COOKING GEAR","product_type":"COOKWARE"},{"main_category":"CAMPING & HIKING","sub_category":"COOKING GEAR","product_type":"UTENSILS & ACCESSORIES"},{"main_category":"CAMPING & HIKING","sub_category":"COOKING GEAR","product_type":"FOOD & NUTRITION"},{"main_category":"CAMPING & HIKING","sub_category":"COOKING GEAR","product_type":"OTHER"},{"main_category":"CAMPING & HIKING","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"CLIMBING","sub_category":"CLIMBING GEAR","product_type":"HARNESSES"},{"main_category":"CLIMBING","sub_category":"CLIMBING GEAR","product_type":"HELMETS"},{"main_category":"CLIMBING","sub_category":"CLIMBING GEAR","product_type":"CARABINERS & QUICKDRAWS"},{"main_category":"CLIMBING","sub_category":"CLIMBING GEAR","product_type":"ROPES & SLINGS"},{"main_category":"CLIMBING","sub_category":"CLIMBING GEAR","product_type":"OTHER"},{"main_category":"CLIMBING","sub_category":"BOULDERING & TRAINING","product_type":"CLIMBING SHOES"},{"main_category":"CLIMBING","sub_category":"BOULDERING & TRAINING","product_type":"CHALK & CHALK BAGS"},{"main_category":"CLIMBING","sub_category":"BOULDERING & TRAINING","product_type":"TRAINING EQUIPMENT"},{"main_category":"CLIMBING","sub_category":"BOULDERING & TRAINING","product_type":"OTHER"},{"main_category":"CLIMBING","sub_category":"MOUNTAINEERING","product_type":"ICE AXES"},{"main_category":"CLIMBING","sub_category":"MOUNTAINEERING","product_type":"CRAMPONS"},{"main_category":"CLIMBING","sub_category":"MOUNTAINEERING","product_type":"MOUNTAINEERING BOOTS"},{"main_category":"CLIMBING","sub_category":"MOUNTAINEERING","product_type":"AVALANCHE SAFETY"},{"main_category":"CLIMBING","sub_category":"MOUNTAINEERING","product_type":"OTHER"},{"main_category":"CLIMBING","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"WATER SPORTS","sub_category":"PADDLING","product_type":"KAYAKS"},{"main_category":"WATER SPORTS","sub_category":"PADDLING","product_type":"CANOES"},{"main_category":"WATER SPORTS","sub_category":"PADDLING","product_type":"PADDLES"},{"main_category":"WATER SPORTS","sub_category":"PADDLING","product_type":"SAFETY GEAR"},{"main_category":"WATER SPORTS","sub_category":"PADDLING","product_type":"OTHER"},{"main_category":"WATER SPORTS","sub_category":"SURFING","product_type":"SURFBOARDS"},{"main_category":"WATER SPORTS","sub_category":"SURFING","product_type":"WETSUITS"},{"main_category":"WATER SPORTS","sub_category":"SURFING","product_type":"RASH GUARDS"},{"main_category":"WATER SPORTS","sub_category":"SURFING","product_type":"SURF ACCESSORIES"},{"main_category":"WATER SPORTS","sub_category":"SURFING","product_type":"OTHER"},{"main_category":"WATER SPORTS","sub_category":"FISHING","product_type":"RODS & REELS"},{"main_category":"WATER SPORTS","sub_category":"FISHING","product_type":"TACKLE"},{"main_category":"WATER SPORTS","sub_category":"FISHING","product_type":"WADERS"},{"main_category":"WATER SPORTS","sub_category":"FISHING","product_type":"ACCESSORIES"},{"main_category":"WATER SPORTS","sub_category":"FISHING","product_type":"OTHER"},{"main_category":"WATER SPORTS","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"WINTER SPORTS","sub_category":"SKIING","product_type":"SKIS"},{"main_category":"WINTER SPORTS","sub_category":"SKIING","product_type":"SKI BOOTS"},{"main_category":"WINTER SPORTS","sub_category":"SKIING","product_type":"SKI POLES"},{"main_category":"WINTER SPORTS","sub_category":"SKIING","product_type":"SKI BINDINGS"},{"main_category":"WINTER SPORTS","sub_category":"SKIING","product_type":"OTHER"},{"main_category":"WINTER SPORTS","sub_category":"SNOWBOARDING","product_type":"SNOWBOARDS"},{"main_category":"WINTER SPORTS","sub_category":"SNOWBOARDING","product_type":"SNOWBOARD BOOTS"},{"main_category":"WINTER SPORTS","sub_category":"SNOWBOARDING","product_type":"BINDINGS"},{"main_category":"WINTER SPORTS","sub_category":"SNOWBOARDING","product_type":"HELMETS"},{"main_category":"WINTER SPORTS","sub_category":"SNOWBOARDING","product_type":"OTHER"},{"main_category":"WINTER SPORTS","sub_category":"SNOWSHOEING","product_type":"SNOWSHOES"},{"main_category":"WINTER SPORTS","sub_category":"SNOWSHOEING","product_type":"POLES"},{"main_category":"WINTER SPORTS","sub_category":"SNOWSHOEING","product_type":"ACCESSORIES"},{"main_category":"WINTER SPORTS","sub_category":"SNOWSHOEING","product_type":"OTHER"},{"main_category":"WINTER SPORTS","sub_category":"OTHER","product_type":"OTHER"},{"main_category":"TRAVEL","sub_category":"LUGGAGE & BAGS","product_type":"TRAVEL BACKPACKS"},{"main_category":"TRAVEL","sub_category":"LUGGAGE & BAGS","product_type":"DUFFEL BAGS"},{"main_category":"TRAVEL","sub_category":"LUGGAGE & BAGS","product_type":"CARRY-ONS"},{"main_category":"TRAVEL","sub_category":"LUGGAGE & BAGS","product_type":"TRAVEL ACCESSORIES"},{"main_category":"TRAVEL","sub_category":"LUGGAGE & BAGS","product_type":"OTHER"},{"main_category":"TRAVEL","sub_category":"TRAVEL ACCESSORIES","product_type":"TRAVEL PILLOWS"},{"main_category":"TRAVEL","sub_category":"TRAVEL ACCESSORIES","product_type":"EYE MASKS"},{"main_category":"TRAVEL","sub_category":"TRAVEL ACCESSORIES","product_type":"PACKING ORGANIZERS"},{"main_category":"TRAVEL","sub_category":"TRAVEL ACCESSORIES","product_type":"SECURITY"},{"main_category":"TRAVEL","sub_category":"TRAVEL ACCESSORIES","product_type":"OTHER"},{"main_category":"TRAVEL","sub_category":"OTHER","product_type":"OTHER"}]

When you query for a sub_category, make sure to always provide the main_category as well, for instance:
SELECT SUM(Number_of_Orders) FROM order_data WHERE main_category = "APPAREL" AND sub_category = "MEN'S CLOTHING" AND Month = 5 AND Year = 2024

When you query for the product_type, make sure to provide the main_category and sub_category as well, for instance:
SELECT SUM(Number_of_Orders) FROM order_data WHERE main_category = "TRAVEL" AND sub_category = "LUGGAGE & BAGS" AND product_type = "TRAVEL BACKPACKS" AND Month = 5 AND Year = 2024

To avoid issues with apostrophes, when referring to categories, always use double-quotes, for instance:
SELECT SUM(Number_of_Orders) FROM order_data WHERE main_category = "APPAREL" AND sub_category = "MEN'S CLOTHING" AND Month = 5 AND Year = 2024

Here are the valid values for the Region:
[{"Region":"NORTH AMERICA"},{"Region":"EUROPE"},{"Region":"ASIA-PACIFIC"},{"Region":"AFRICA"},{"Region":"MIDDLE EAST"},{"Region":"SOUTH AMERICA"}]
                 """


@tool
def sales_data_insights(question: str):
    """
    get some data insights about the contoso sales data. This tool has information about total sales, return return rates, discounts given, etc., by date, product category, etc.
    you can ask questions like:
    - query for the month with the strongest revenue
    - which day of the week has the least sales in january
    - query the average value of orders by month
    - what is the average sale value for Tuesdays
    If a query cannot be answered, the tool will return a message saying that the query is not supported. otherwise the data will be returned.
    """

    client  = AzureOpenAI(
        api_key = os.getenv("OPENAI_API_KEY"),
        azure_endpoint = os.getenv("OPENAI_API_BASE"),
        api_version = os.getenv("OPENAI_API_VERSION")
    )

    print("getting sales data insights")
    print("question", question)

    messages = [{"role": "system", 
                 "content": system_message}]
    
    messages.append({"role": "user", "content": f"{question}\nGive only the query in SQL format"})

    response = client.chat.completions.create(
        model= os.getenv("OPENAI_ANALYST_CHAT_MODEL"),
        messages=messages, 
    )

    message = response.choices[0].message

    query :str = message.content

    if query.startswith("```sql") and query.endswith("```"):
        query = query[6:-3].strip()

    ## get folder of this file -- below which is the data folder
    folder = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(f'{folder}/data/order_data.db')

    try:
        df = pd.read_sql(query, con)
    except Exception as e:
        return {"data": None, "error": f"{e}", "query": query}

    data = df.to_dict(orient='records')
    return {"data": data, "error": None, "query": query}

 
def main():
    from promptflow.tracing import start_trace
    start_trace()
    result = sales_data_insights(question="what are the sales numbers aggregated by country for feb by category")
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    main()


