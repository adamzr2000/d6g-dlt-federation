# demo.py
import time
from typing import List
from web3 import Web3
from prettytable import PrettyTable
import logging
import utils
from blockchain_interface import FederationEvents

logger = logging.getLogger(__name__)

STEP_HEADER = ["step", "t_rel"]

def run_consumer_federation_demo(app, services_to_announce, expected_hours, offers_to_wait, export_to_csv, csv_path):
    data = []
    header = STEP_HEADER
    blockchain = app.state.blockchain
    provider_flag = app.state.provider_flag

    # monotonic base
    rel0 = time.perf_counter()

    # ---------- tiny helpers ----------
    def mark(step):
        t_rel = time.perf_counter() - rel0
        data.append([step, t_rel])
        return t_rel

    def wait_for_bids(service_id: str, min_offers: int):
        bids_event = blockchain.create_event_filter(FederationEvents.NEW_BID)
        logger.info("⏳ Waiting for bids...")
        while True:
            for event in bids_event.get_all_entries():
                event_service_id = Web3.toText(event["args"]["serviceId"]).rstrip("\x00")
                received_bids = int(event["args"]["biderIndex"])
                if event_service_id == service_id and received_bids >= min_offers:
                    logger.info(f"📨 {received_bids} bid(s) received:")
                    return received_bids
            time.sleep(0.1)

    def show_bids_and_pick_best(service_id: str, received_bids: int):
        table = PrettyTable()
        table.field_names = ["Bid Index", "Provider Address", "Price (Wei/hour)", "Location"]

        lowest_price = None
        best_bid_index = None
        chosen_price = None

        for i in range(received_bids):
            provider_addr, bid_price_raw, bid_index_raw, location = blockchain.get_bid_info(service_id, i)
            bid_price = int(bid_price_raw)
            bid_index = int(bid_index_raw)
            table.add_row([bid_index, provider_addr, bid_price, location])

            if lowest_price is None or bid_price < lowest_price:
                lowest_price = bid_price
                best_bid_index = bid_index
                chosen_price = bid_price

        print(table)
        return best_bid_index, chosen_price

    def wait_for_state(service_id: str, target_state: int = 2):
        logger.info("⏳ Waiting for provider to complete deployment...")
        while blockchain.get_service_state(service_id) != target_state:
            time.sleep(0.1)
    # ---------- start ----------

    t_start = mark("start")

    # --- Federation negotiation and execution for service1 and service2 ---
    for key in ("service1", "service2"):
        service = services_to_announce[key]

        # Announce
        mark(f"{key}_announced")
        tx_hash, service_id = blockchain.announce_service(
            service["description"],
            service["requirements"][0],
            service["requirements"][1],
            service["requirements"][2],
            service["requirements"][3],
            service["requirements"][4],
            service["requirements"][5],
        )
        logger.info(f"📢 Service announcement sent (Service ID: '{service_id}', Description: {service['description']})")

        # Bids
        bids_count = wait_for_bids(service_id, offers_to_wait)
        mark(f"{key}_bid_offer_received")

        # Choose winner
        best_bid_index, chosen_price = show_bids_and_pick_best(service_id, bids_count)
        mark(f"{key}_winner_chosen")
        tx_hash = blockchain.choose_provider(service_id, best_bid_index, expected_hours, expected_hours * chosen_price)
        logger.info(f"🏆 Provider selected (Bid index: {best_bid_index})")

        # Send deployment info
        mark(f"{key}_deploy_info_sent_to_provider")
        tx_hash = blockchain.update_endpoint(service_id, provider_flag, service["deployment_manifest_cid"])
        if key == "service1":
            logger.info("Endpoint information for DetNet-PREOF connectivity shared")
        else:
            logger.info("Endpoint information for VXLAN connection and ROS app manifest shared")

        # Wait for deployment confirmation
        wait_for_state(service_id, target_state=2)
        mark(f"{key}_confirm_deploy_received")
        logger.info("✅ Deployment confirmation received")
        print()

    # Federated service info
    while not blockchain.is_provider_endpoint_set(service_id):
        time.sleep(0.1)
    _desc, _cid = blockchain.get_service_info(service_id, provider_flag)
    mark(f"{key}_get_deploy_info_from_provider")
    # logger.info(f"Deployment manifest IPFS CID: {_cid}")

    # Connectivity setup & test
    mark("establish_connection_with_provider_start")
    logger.info("🌐 Creating VXLAN connecton with the provider...")
    time.sleep(1)
    mark("establish_connection_with_provider_finished")

    logger.info("🌐 Testing connectivity with federated instance...")
    time.sleep(1)
    mark("e2e_service_running")

    t_rel_end = mark("end")  # final timestamp
    logger.info("✅ Federation(s) #1 and #2 successfully completed in {:.2f} seconds.".format(t_rel_end))

    if export_to_csv:
        utils.create_csv_file(csv_path, header, data)

    return {"status": "success", "duration_s": round(t_rel_end, 2)}


def run_provider_federation_demo(app, price_wei_per_hour, location, description_filter, export_to_csv, csv_path):
    header = STEP_HEADER
    data = []
    blockchain = app.state.blockchain
    provider_flag = app.state.provider_flag

    rel0 = time.perf_counter()

    # ---------- helpers ----------
    def mark(step):
        t_rel = time.perf_counter() - rel0
        data.append([step, t_rel])
        return t_rel

    DESC_DETNET = "detnet_transport"
    DESC_K8S = "ros_app_k8s_deployment"
    SIMPLE_MAP = {DESC_DETNET: "service1", DESC_K8S: "service2"}

    def map_desc_to_simple(desc: str) -> str:
        return SIMPLE_MAP.get(desc, "")  # preserve original fallback ""

    def print_announcement_table(service_id: str, description: str, requirements):
        table = PrettyTable()
        table.title = "📨 New service announcement received"
        table.field_names = ["Field", "Value"]
        table.align["Field"] = "l"
        table.align["Value"] = "l"
        table.add_row(["Service ID", service_id])
        table.add_row(["Description", description])
        table.add_row(["Availability", requirements[0]])
        table.add_row(["Max Latency (ms)", requirements[1]])
        table.add_row(["Max Jitter (ms)", requirements[2]])
        table.add_row(["Min Bandwidth (Mbps)", requirements[3]])
        table.add_row(["CPU (millicores)", requirements[4]])
        table.add_row(["RAM (MB)", requirements[5]])
        print(table)

    # ---------- start ----------
    mark("start")
    open_services = []
    seen_open_ids = set()      # to avoid re-adding the same open service
    seen_other = set()

    # Initialize simplified id according to the (optional) filter — identical logic.
    service_id_simplified = map_desc_to_simple(description_filter) if description_filter else ""

    new_service_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT)
    logger.info("🔎 Watching federation events...")

    # Wait until we see at least one open service
    while True:
        new_events = new_service_event.get_all_entries()
        for event in new_events:
            args = event["args"]
            service_id = Web3.toText(args["serviceId"]).rstrip("\x00")
            description = args["description"]
            state = blockchain.get_service_state(service_id)
            simplified = map_desc_to_simple(description)

            if state != 0:
                continue  # only care about open services

            # (1) Matches filter (or no filter) → show & collect once per service ID
            if description_filter is None or description == description_filter:
                if service_id not in seen_open_ids:
                    requirements = blockchain.get_service_requirements(service_id)
                    open_services.append((service_id, simplified))
                    print_announcement_table(service_id, description, requirements)
                    seen_open_ids.add(service_id)

            # (2) Non-matching announcements: mark/log only once
            elif simplified not in seen_other:
                mark("{}_other_announce_received".format(simplified))
                requirements = blockchain.get_service_requirements(service_id)
                print_announcement_table(service_id, description, requirements)
                logger.info("⚠️ Not able to provide this service. Ignoring announcement...")
                seen_other.add(simplified)

        if open_services:
            _, selected_simplified = open_services[-1]
            # First time we have at least one open service
            mark("{}_announce_received".format(selected_simplified))
            break
        time.sleep(0.1)

    # Select the latest open service (unchanged)
    service_id, service_id_simplified = open_services[-1]

    # Place bid
    mark("{}_bid_offer_sent".format(service_id_simplified))
    blockchain.place_bid(service_id, price_wei_per_hour, location)
    logger.info(f"💰 Bid offer sent (Service ID: '{service_id}', Price: {price_wei_per_hour} Wei/hour)")

    # Wait for winner
    logger.info("⏳ Waiting for a winner to be selected...")
    winner_chosen_event = blockchain.create_event_filter(FederationEvents.SERVICE_ANNOUNCEMENT_CLOSED)
    while True:
        new_events = winner_chosen_event.get_all_entries()
        matched = any(
            Web3.toText(e["args"]["serviceId"]).rstrip("\x00") == service_id
            for e in new_events
        )
        if matched:
            mark("{}_winner_received".format(service_id_simplified))
            break
        time.sleep(0.1)

    # Deployment path selection (kept identical)
    service_to_deploy = DESC_DETNET if service_id_simplified == "service1" else DESC_K8S

    # If this provider is the winner
    if blockchain.is_winner(service_id):
        logger.info(f"🏆 Selected as the winner for '{service_id}'")
        mark("{}_deploy_start".format(service_id_simplified))

        while not blockchain.is_consumer_endpoint_set(service_id):
            time.sleep(0.1)
        _desc, _cid = blockchain.get_service_info(service_id, provider_flag)
        mark("{}_get_deploy_info_from_consumer".format(service_id_simplified))
        logger.info(f"Consumer deploy info: {_cid}")

        if service_to_deploy == DESC_DETNET:
            logger.info("🌐 Enabling DetNet-PREOF capabilities in the transport network...")

            mark("{}_deploy_finished".format(service_id_simplified))
            mark("{}_confirm_deploy_sent".format(service_id_simplified))
            blockchain.service_deployed(service_id)
            logger.info("✅ Service deployed")

        else:
            logger.info("🌐 Creating VXLAN connecton with the consumer...")

            logger.info("🚀 Deploying ROS application container on Kubernetes...")

            mark("{}_deploy_finished".format(service_id_simplified))

            # Send deployment info
            mark("{}_deploy_info_sent_to_consumer".format(service_id_simplified))
            deployment_manifest_cid = "QmExampleCIDForK8sDeploymentManifest"
            blockchain.update_endpoint(service_id, provider_flag, deployment_manifest_cid)
            logger.info("VXLAN endpoint shared.")

            mark("{}_confirm_deploy_sent".format(service_id_simplified))
            blockchain.service_deployed(service_id)
            logger.info("✅ Service deployed")

    else:
        logger.info(f"❌ Not selected as the winner for '{service_id}'")
        mark("{}_other_provider_chosen".format(service_id_simplified))

        if export_to_csv:
            utils.create_csv_file(csv_path, header, data)

        return {"message": f"Another provider was chosen for '{service_id}'"}

    t_rel_end = mark("end")

    if export_to_csv:
        utils.create_csv_file(csv_path, header, data)

    return {"status": "success", "duration_s": round(t_rel_end, 2)}
