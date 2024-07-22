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
from typing import Any, Generator, Optional, Set, Type, cast

from packages.valory.contracts.gnosis_safe.contract import GnosisSafeContract
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
            price = yield from self.get_price()
            payload = APICheckPayload(sender=sender, price=price)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_price(self):
        """Get token price from Coingecko"""
        response = yield from self.get_http_response(
            method="GET",
            url=self.params.coingecko_price_template,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-cg-demo-api-key": self.params.coingecko_api_key,
            },
        )
        if response.status_code != 200:
            self.context.logger.error(
                f"Error in fetch the price,Status_code{response.status_code}"
            )

        try:
            response_body = response.body
            response_data = json.loads(response_body)
            price = response_data["autonolas"]["usd"]
            self.context.logger.info(f"The price is {price}")
            return price
        except json.JSONDecodeError:
            self.context.logger.error("Could not parse the response body")
            return None


class DecisionMakingBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            event = yield from self.get_next_event()
            self.context.logger.info(f"evnt behaviour:{event}")
            payload = DecisionMakingPayload(sender=sender, event=event)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    @staticmethod
    def init(now: datetime) -> float:
        return now.timestamp()

    def get_next_event(self) -> Generator[None, None, Optional[str]]:
        """Get the next event"""
        # Using the token price from the previous round, decide whether we should make a transfer or not
        block_number = yield from self.get_block_number()

        # if fail to get block number, we send the ERROR event
        if not block_number:
            self.context.logger.info("Block number is None.Sending the ERROR event...")
            return Event.ERROR.value

        # if we fail to get the token price , we send ERROR event
        token_price = self.synchronized_data.price
        if not token_price:
            self.context.logger.info("Token price is None. Sending the ERROR event...")
            return Event.ERROR.value
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
        self.context.logger.info("Passing the TRANSACT event...")
        return Event.TRANSACT.value


    # ledger Interaction
    def get_block_number(self) -> Generator[None, None, Optional[int]]:
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_block_number",
            chain_id=GNOSIS_CHAIN_ID,
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retieving block number: {ledger_api_response}"
            )
            return None

        block_number = cast(
            int, ledger_api_response.state.body["get_block_number_result"]
        )

        self.context.logger.error(f"Got block number: {block_number}")

        return block_number

    def get_sync_timestamp(self) -> float:
        now = cast(
            SharedState(skill_context=self.context)
        )._round_sequence.last_round_transition_timestamp.timestamp()

        return now


class TxPreparationBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """TxPreparationBehaviour"""

    matching_round: Type[AbstractRound] = TxPreparationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            tx_hash = yield from self.get_tx_hash()
            payload = TxPreparationPayload(
                sender=sender, tx_submitter=None, tx_hash=tx_hash
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _build_safe_tx_hash(
        self, **kwargs: Any
    ) -> Generator[None, None, Optional[str]]:

        self.context.logger.info(
            f"Preparing Transfer for safe [{self.synchronized_data.safe_contract_address}]:{kwargs}"
        )

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            data=TX_DATA,
            safe_tx_gas=SAFE_GAS,
            chain_id=GNOSIS_CHAIN_ID,
            **kwargs,
        )

        self.context.logger.info(f"APPROVE TXN: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get safe tx hash."
                f"Expected response performative {ContractApiMessage.Performative.STATE.value!r}, "
                f"received {response.performative.value!r}."
            )
            return None

        tx_hash = response.state.body.get("tx_hash", None)
        if tx_hash is None:
            self.context.logger.error(
                "Something went wrong while trying to get the transaction's hash. "
                f"invalid hash {tx_hash!r} was returned"
            )
            return None

        return tx_hash[2:]  # strip 0x from response hash

    def get_tx_hash(self) :
        """Get the tx hash"""
        # We need to prepare a 1 wei transfer from the safe to another (configurable) account.
        call_data = {VALUE_KEY: 1, TO_ADDRESS_KEY: self.params.transfer_target_address}

        safe_tx_hash = yield from self._build_safe_tx_hash(**call_data)
        if safe_tx_hash is None:
            self.context.logger.error("could not build the safe transaction's hash")
            return None
        tx_hash = hash_payload_to_hex(
            safe_tx_hash,
            call_data[VALUE_KEY],
            SAFE_GAS,
            call_data[TO_ADDRESS_KEY],
            TX_DATA,
        )
        self.context.logger.info(f"Transaction hash is {tx_hash}")
        return tx_hash


class LearningRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = APICheckBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        APICheckBehaviour,
        DecisionMakingBehaviour,
        TxPreparationBehaviour,
    ]
