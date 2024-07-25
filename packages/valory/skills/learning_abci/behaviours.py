# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains round behaviours of LearningAbciApp."""

from abc import ABC
from typing import Any, Generator, Optional, Set, Type, cast, Optional, Dict, Any, Tuple, Union
from hexbytes import HexBytes
from packages.valory.contracts.donation_manager.contract import DonationManagerContract

from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation
)

from packages.valory.contracts.multisend.contract import(
    MultiSendContract,
    MultiSendOperation,
)
from packages.valory.protocols.contract_api.message import ContractApiMessage
from packages.valory.protocols.ledger_api.message import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.learning_abci.models import Params, SharedState
from packages.valory.skills.learning_abci.payloads import (
    APICheckPayload,
    DecisionMakingPayload,
    TxPreparationPayload,
)
from packages.valory.skills.learning_abci.rounds import (
    APICheckRound,
    DecisionMakingRound,
    Event,
    LearningAbciApp,
    SynchronizedData,
    TxPreparationRound,
    DonationAction
)
import json
from datetime import datetime


from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)


HTTP_OK = 200
GNOSIS_CHAIN_ID = "gnosis"
TX_DATA = b"0x"
SAFE_GAS = 0
VALUE_KEY = "value"
TO_ADDRESS_KEY = "to_address"
MULTISEND_ADDRESS= "0xA238CBeb142c10Ef7Ad8442C6D1f9E89e07e7761"


class LearningBaseBehaviour(BaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """Base behaviour for the learning_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
        """Return the params."""
        return cast(Params, super().params)

    @property
    def local_state(self) -> SharedState:
        """Return the state."""
        return cast(SharedState, self.context.state)


class APICheckBehaviour(LearningBaseBehaviour):  # pylint: disable=too-many-ancestors
    """APICheckBehaviour"""

    matching_round: Type[AbstractRound] = APICheckRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            #price = yield from self.get_price()
            #payload = APICheckPayload(sender=sender, price=price)
            #add ipfs
            donation_amount= yield from self.get_donation_amount()
            self.context.logger.info(f"DONATION AMOUNT RETRIEVED - {donation_amount}")
            donation_rules= {
                "user_id" : "user123",
                "rules":{
                    "minimum_donation": 10,
                    "maximum_donation": 1000
                }
            }
            ipfs_hash= yield from self.send_to_ipfs(
                "donation-rules.json",
                {"donation-rules": donation_rules},
                filetype= SupportedFiletype.JSON

            )
            self.context.logger.info(f"IPFS HASH- {ipfs_hash}")
            payload= APICheckPayload(sender=sender, amount= donation_amount , ipfs_hash=ipfs_hash) #complete

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
    
    def get_donation_amount(self) -> Generator[None, None, Optional[int]]:
        response = yield from self.get_http_response(
            method="GET",
            url=self.params.donation_amount_api_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.params.api_key}",
            },
        )

        if response.status_code != 200:
            self.context.logger.error(f"Error fetching donation amount with status code {response.status_code}")
            return None

        decoded_response = response.body

        try:
            response_data = json.loads(decoded_response)
            donation_amount = response_data['donation']['amount']
            return donation_amount
        except json.JSONDecodeError:
            self.context.logger.error("APICheckBehaviour: Could not parse the response body!") 
            return None 



class DecisionMakingBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            decision, donation_amount= yield from self.make_donation_decision()
            self.context.logger.info(f"DECISION MADE: {decision}")
            sender = self.context.agent_address
            payload = DecisionMakingPayload(sender=sender, decision=decision, donation_amount= donation_amount)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
#approve logic
    def make_donation_decision(self) -> Generator[None,None,str]:
        response= yield from self.get_contract_api_response(
            perormative=ContractApiMessage.Performative.GET_STATE,
            contract_id=str(DonationManager.contract_id),
            contract_callable="getDonations",
            contract_address= self.params.donation_manager_contract_address
        )
        donation= response.state.body['data']
        self.context.logger.info(f"DONATIONS RETRIEVED FROM CONTRACT : {donations}")

        for donation in donations:
            if not donation['approved'] and self.should_approve(donation):
                return "APPROVE", donation['amount']
        return "NO_APPROVAL", 0

    def should_approve(self, donation: dict) -> bool:
        min_donation = self.params.min_donation
        max_donation= self.params.max_donation

        if min_donation <= donation['amount'] <= max_donation:
            return True
        return False    







   # @staticmethod
    #def init(now: datetime) -> float:
     #   return now.timestamp()

  #  def get_next_event(self) -> Generator[None, None, Optional[str]]:
   #     """Get the next event"""
        # Using the token price from the previous round, decide whether we should make a transfer or not
    #    block_number = yield from self.get_block_number()

        # if fail to get block number, we send the ERROR event
     #   if not block_number:
      #      self.context.logger.info("Block number is None.Sending the ERROR event...")
       #     return Event.ERROR.value

        # if we fail to get the token price , we send ERROR event
        #token_price = self.synchronized_data.price
        #if not token_price:
         #   self.context.logger.info("Token price is None. Sending the ERROR event...")
          #  return Event.ERROR.value
        # # if the timestamp does not end in 0, we send the DONE event
        # now = self.get_sync_timestamp()
        # self.context.logger.info("Timestamp is {now}")

        # if self.init(now) % 5 != 0:
        #     self.context.logger.info(
        #          f"Timestamp [{self.init(now)}] is not divisible by 5, Sending DONE event..."
        #     )
        #     return Event.TRANSACT.value
        # return Event.DONE.value
        # Directly passing Event.TRANSACT.value
        #self.context.logger.info("Passing the TRANSACT event...")
        #return Event.TRANSACT.value


    # ledger Interaction
 #   def get_block_number(self) -> Generator[None, None, Optional[int]]:
  #      ledger_api_response = yield from self.get_ledger_api_response(
   #         performative=LedgerApiMessage.Performative.GET_STATE,
    #        ledger_callable="get_block_number",
     #       chain_id=GNOSIS_CHAIN_ID,
      #  )

       # if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
        #    self.context.logger.error(
         #       f"Error while retieving block number: {ledger_api_response}"
          #  )
           # return None

    #    block_number = cast(
    #        int, ledger_api_response.state.body["get_block_number_result"]
    #    )

     #   self.context.logger.error(f"Got block number: {block_number}")
#
 #       return block_number

  #  def get_sync_timestamp(self) -> float:
   #     now = cast(
    #        SharedState(skill_context=self.context)
     #   )._round_sequence.last_round_transition_timestamp.timestamp()

      #  return now


class TxPreparationBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """TxPreparationBehaviour"""

    matching_round: Type[AbstractRound] = TxPreparationRound
    ETHER_VALUE= 0
    DONATION_MANAGER_ADDRESS= " " #add adrress
    AMOUNT= 10**18 #example amount

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            #sender = self.context.agent_address
            #tx_hash = yield from self.get_tx_hash()
            #payload = TxPreparationPayload(
            #    sender=sender, tx_submitter=None, tx_hash=tx_hash
            #)
            update_payload= yield from self.get_transaction_update()

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            payload= TxPreparationPayload(
                self.context.agent_address,
                update_payload
            )
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_transaction_update(self) -> Generator[None,None, str]:   
        rules = yield from self.get_from_ipfs(
            self.synchronized_data.ipfs_hash, filetype=SupportedFiletype.JSON
        )
        self.context.logger.info(f"DATA RETRIEVED FROM IPFS {rules}")

        decision = self.synchronized_data.decision
        
        if decision == DonationAction.APPROVE.value:
            safe_txn = yield from self._build_approve_txn()
            return safe_txn
        
        elif decision == DonationAction.EXECUTE.value:
            transactions = yield from self._build_execute_and_approve_txns()
            if transactions is None:
                return "{}"
            
            payload_data = yield from self._get_multisend_tx(transactions)
            self.context.logger.info(f"MULTISEND TRANSACTIONS {payload_data}")
            if payload_data is None:
                return "{}"
            return payload_data

    def _build_approve_txn(self) -> Generator[None,None,str]:
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(DonationManagerContract.contract_id),
            contract_callable="build_approval_tx",
            contract_address=self.DONATION_MANAGER_ADDRESS,
            amount=self.AMOUNT
        )

        self.context.logger.info(f"APPROVE TXN: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehavior says: Couldn't get tx data for the txn. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "
                f"received {response.performative.value}."
            )
            return "{}"

        data_str = cast(str, response.state.body["data"])[2:]
        txn = bytes.fromhex(data_str)

        if txn is None:
            return "{}"

        safe_tx_hash = yield from self._get_safe_tx_hash(
            txn,
            self.DONATION_MANAGER_ADDRESS
        )

        if safe_tx_hash is None:
            return "{}"

        payload_data = hash_payload_to_hex(
            safe_tx_hash=safe_tx_hash,
            to_address=self.DONATION_MANAGER_ADDRESS,
            ether_value=self.ETHER_VALUE,
            safe_tx_gas=SAFE_GAS,
            data=txn,
        )

        return payload_data

    def _build_execute_txn(self) -> Generator[None, None, Optional[bytes]]:
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(DonationManagerContract.contract_id),
            contract_callable="build_execute_tx",
            contract_address=self.DONATION_MANAGER_ADDRESS,
            amount=self.AMOUNT
        )

        self.context.logger.info(f"EXECUTE TXN: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehavior says: Couldn't get tx data for the txn. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "
                f"received {response.performative.value}."
            )
            return None

        data_str = cast(str, response.state.body["data"])[2:]
        data = bytes.fromhex(data_str)
        return data

    def _build_approve_and_execute_txns(self) -> Generator[None, None, Optional[List[bytes]]]:
        transactions: List[bytes] = []

        approve_tx_data = yield from self._build_approve_txn()
        if approve_tx_data is None:
                return None      
        transactions.append(approve_tx_data)

        execute_tx_data = yield from self._build_execute_txn()
        if execute_tx_data is None:
                return None      
        transactions.append(execute_tx_data)

        return transactions        

    def _get_safe_tx_hash(self, data: bytes, to_address: str, is_multisend: bool = False) -> Generator[None, None, Optional[str]]:
        contract_api_kwargs = {
            "performative": ContractApiMessage.Performative.GET_STATE,  # type: ignore
            "contract_address": self.synchronized_data.safe_contract_address,  # the safe contract address
            "contract_id": str(GnosisSafeContract.contract_id),
            "contract_callable": "get_raw_safe_transaction_hash",
            "to_address": to_address,
            "value": self.ETHER_VALUE,
            "data": data,
            "safe_tx_gas": SAFE_GAS,
        }
        
        if is_multisend:
            contract_api_kwargs["operation"] = SafeOperation.DELEGATE_CALL.value

        response = yield from self.get_contract_api_response(**contract_api_kwargs)

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehavior says: Couldn't get safe hash. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "
                f"received {response.performative.value}."
            )
            return None

        tx_hash = cast(str, response.state.body["tx_hash"])[2:]
        return tx_hash

    def _get_multisend_tx(self, txs: List[bytes]) -> Generator[None, None, Optional[str]]:
        """Given a list of transactions, bundle them together in a single multisend tx."""
        multi_send_txs = []

        multi_send_approve_tx = self._to_multisend_format(txs[0], self.DONATION_MANAGER_ADDRESS)
        multi_send_txs.append(multi_send_approve_tx)

        multi_send_execute_tx = self._to_multisend_format(txs[1], self.DONATION_MANAGER_ADDRESS)
        multi_send_txs.append(multi_send_execute_tx)

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=MULTISEND_ADDRESS,
            contract_id=str(MultiSendContract.contract_id),
            contract_callable="get_tx_data",
            multi_send_txs=multi_send_txs,
        )

        self.context.logger.info(f"PREPARED MULTISEND TXN:{response}")

        if response.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Couldn't compile the multisend tx. "
                f"Expected response performative {ContractApiMessage.Performative.RAW_TRANSACTION.value}, "
                f"received {response.performative.value}."
            )
            return None

        multisend_data_str = cast(str, response.raw_transaction.body["data"])[2:]
        tx_data = bytes.fromhex(multisend_data_str)
        tx_hash = yield from self._get_safe_tx_hash(tx_data, MULTISEND_ADDRESS, is_multisend=True)
        
        if tx_hash is None:
            return None

        payload_data = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=self.ETHER_VALUE,
            safe_tx_gas=SAFE_GAS,
            operation=SafeOperation.DELEGATE_CALL.value,
            to_address=MULTISEND_ADDRESS,
            data=tx_data,
        )
        return payload_data

    def _to_multisend_format(self, single_tx: bytes, to_address) -> Dict[str, Any]:
        """This method puts tx data from a single tx into the multisend format."""
        multisend_format = {
            "operation": MultiSendOperation.CALL,
            "to": to_address,
            "value": self.ETHER_VALUE,
            "data": HexBytes(single_tx),
        }
        return multisend_format

         


class LearningRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = APICheckBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        APICheckBehaviour,
        DecisionMakingBehaviour,
        TxPreparationBehaviour,
    ]
