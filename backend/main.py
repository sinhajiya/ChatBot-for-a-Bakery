from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
import db_handler
import importlib
import other_fns
from fastapi.staticfiles import StaticFiles

app = FastAPI()

static_directory = r"\backend\static"

app.mount("/static", StaticFiles(directory=static_directory), name="static")

inprogress_order = {}


@app.post("/")
async def handle_request(request: Request):
    try:
        payload = await request.json()
        intent = payload['queryResult']['intent']['displayName']
        parameters = payload['queryResult']['parameters']
        output_contexts = payload['queryResult']['outputContexts']
        session_id = other_fns.extract_session_id(output_contexts[0]['name'])

        intent_dict = {
            "order.add-context:ongoing-order": add,
            "order.complete-context:ongoing-order": complete,
            "track.order-context:ongoing-tracking": track,
            "order.remove-context:ongoing-order": remove
        }

        return intent_dict[intent](parameters, session_id)


    except KeyError as e:
        return JSONResponse(status_code=400, content={"error": f"KeyError: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

def add(parameters: dict, session_id: str):
    menu_items = parameters['menu_items']
    number = parameters["number"]
    if len(menu_items) != len(number):
        fulfillment_text = "Sorry I didn't understand. Can you please specify food items and quantities clearly?"
    else:
        new_food_dict = dict(zip(menu_items, number))

        if session_id in inprogress_order:
            current_food_dict = inprogress_order[session_id]
            current_food_dict.update(new_food_dict)
            inprogress_order[session_id] = current_food_dict
        else:
            inprogress_order[session_id] = new_food_dict
        order = other_fns.get_str_from_food_dict(inprogress_order[session_id])

        fulfillment_text = f"Ok! Your order contains {order}. Do you want to add anything else?"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def complete(parameters: dict, session_id: str):
    if session_id not in inprogress_order:
        fulfillment_text = "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
    else:
        order = inprogress_order[session_id]
        order_id = save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. " \
                               "Please place a new order again"
        else:
            order_total = db_handler.get_total_order_price(order_id)

            fulfillment_text = f"Awesome. We have placed your order. " \
                               f"Here is your order id # {order_id}. " \
                               f"Your order total is {order_total} which you can pay at the time of delivery!"

        del inprogress_order[session_id]

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def remove(parameters: dict, session_id: str):
    if session_id not in inprogress_order:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
        })

    food_items = parameters["menu_items"]
    current_order = inprogress_order[session_id]
    removed_items = []
    no_such_items = []
    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed {",".join(removed_items)} from your order!'

    if len(no_such_items) > 0:
        fulfillment_text = f' Your current order does not have {",".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " Your order is now empty!"
    else:
        order_str = other_fns.get_str_from_food_dict(current_order)
        fulfillment_text += f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })


def track(parameters: dict, session_id: str):
    importlib.reload(db_handler)
    order_id = int(parameters['order_id'])
    order_status = db_handler.get_order_status(order_id)
    if order_status:
        fulfillment_text = f"The order status for order id: {order_id} is: {order_status}"
    else:
        fulfillment_text = f"No order found with order id: {order_id}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def save_to_db(order: dict):
    next_order_id = db_handler.get_next_order_id()
    for food_item, quantity in order.items():
        rcode = db_handler.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )

        if rcode == -1:
            return -1
    db_handler.insert_order_tracking(next_order_id, "in progress")

    return next_order_id
