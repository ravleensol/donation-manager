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

"""This package contains the rounds of LearningAbciApp."""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.learning_abci.payloads import (
    APICheckPayload,
    DecisionMakingPayload,
    TxPreparationPayload,
)


class Event(Enum):
    """LearningAbciApp Events"""

    DONE = "done"
    ERROR = "error"
    TRANSACT = "transact"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    APPROVE_DONATION: "approve_donation"
    REJECT_DONATION: "reject_donation"
    DONATION_RECIEVED: "donation_recieved"

class DonationAction(Enum):
    HOLD="hold"
    APPROVE="approve"
    REJECT="reject"
    PROCESS="process"
    FINALIZE="finalize"    


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    def donation_status(self) -> Optional[str]:
        """getdonation status"""
        return self.db.get("donation_status", None)    

    @property
    def donation_amount(self) -> Optional[int]:
        """Get the donation_amount"""
        return self.db.get("donation_amount", None)

    @property
    def participant_to_donation_round(self) -> DeserializedCollection:
        """Get the participants to the donation round."""
        return self._get_deserialized("participant_to_donation_round")

    @property
    def most_voted_donation(self) -> Optional[int]:
        """Get the token most_voted_donation."""
        return self.db.get("most_voted_donation", None)

    @property
    def participant_to_tx_round(self) -> DeserializedCollection:
        """Get the participants to the tx round."""
        return self._get_deserialized("participant_to_tx_round")

    @property
    def tx_submitter(self) -> str:
        """Get the round that submitted a tx to transaction_settlement_abci."""
        return str(self.db.get_strict("tx_submitter"))

    @property
    def ipfs_hash(self) -> Optional[str]:
        """Get IPFS hash value"""    
        return self.db.get("ipfs_hash", None)

    @property
    def decision(self) -> Optional[str]:
        """Get decision value"""
        return self.db.get("decision", None)

    @property
    def participant_to_decision_round(self) -> Optional[str]:
        """Get participant_to_decision_round value"""
        return self._get_deserialized("participant_to_decision_round")



#fetch
class APICheckRound(CollectSameUntilThresholdRound):
    """APICheckRound"""

    payload_class = APICheckPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_donation_round)
    selection_key = (get_name(SynchronizedData.donation_amount), get_name(SynchronizedData.ipfs_hash))

    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class DecisionMakingRound(CollectSameUntilThresholdRound):
    """DecisionMakingRound"""

    payload_class = DecisionMakingPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            event = Event.ERROR
            if self.most_voted_payload == "APPROVE":
                event = Event.TRANSACT
            elif self.most_voted_payload == "REJECT":
                event = Event.DONE

            synchronized_data = cast(
                SynchronizedData,
                self.synchronized_data.update(
                    synchronized_data_class=self.synchronized_data_class,
                    **{get_name(SynchronizedData.decision): self.most_voted_payload},
                ),
            )
            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None    

        

    # Event.DONE, Event.ERROR, Event.TRANSACT, Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class TxPreparationRound(CollectSameUntilThresholdRound):
    """TxPreparationRound"""

    payload_class = TxPreparationPayload
    synchronized_data_class = SynchronizedData
    ERROR_PAYLOAD = "{}"

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            if self.most_voted_payload == self.ERROR_PAYLOAD:
                return self.synchronized_data, Event.ERROR

            state = self.synchronized_data.update(
                synchronized_data_class=self.synchronized_data_class,
                **{
                    get_name(
                        SynchronizedData.participant_to_donation_round
                    ): self.serialize_collection(self.collection),
                    get_name(
                        SynchronizedData.decision
                    ): self.most_voted_payload,
                    get_name(SynchronizedData.tx_submitter): self.auto_round_id(),
                },
            )
            return state, Event.DONE
        
        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None
    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class FinishedDecisionMakingRound(DegenerateRound):
    """FinishedDecisionMakingRound"""


class FinishedTxPreparationRound(DegenerateRound):
    """FinishedLearningRound"""


class LearningAbciApp(AbciApp[Event]):
    """LearningAbciApp"""

    initial_round_cls: AppState = APICheckRound
    initial_states: Set[AppState] = {
        APICheckRound,
    }
    transition_function: AbciAppTransitionFunction = {
        APICheckRound: {
            Event.NO_MAJORITY: APICheckRound,
            Event.ROUND_TIMEOUT: APICheckRound,
            Event.DONE: DecisionMakingRound,
        },
        DecisionMakingRound: {
            Event.NO_MAJORITY: DecisionMakingRound,
            Event.ROUND_TIMEOUT: DecisionMakingRound,
            Event.DONE: FinishedDecisionMakingRound,
            Event.ERROR: FinishedDecisionMakingRound,
            Event.TRANSACT: TxPreparationRound,
            Event.APPROVE_DONATION: TxPreparationRound,
            Event.REJECT_DONATION: FinishedDecisionMakingRound,
        },
        TxPreparationRound: {
            Event.NO_MAJORITY: TxPreparationRound,
            Event.ROUND_TIMEOUT: TxPreparationRound,
            Event.DONE: FinishedTxPreparationRound,
            Event.ERROR: FinishedDecisionMakingRound
        },
        FinishedDecisionMakingRound: {},
        FinishedTxPreparationRound: {},
    }
    final_states: Set[AppState] = {
        FinishedDecisionMakingRound,
        FinishedTxPreparationRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        APICheckRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedDecisionMakingRound: set(),
        FinishedTxPreparationRound: {get_name(SynchronizedData.most_voted_donation)},
    }
