from typing import Any, Dict, Optional, cast

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import LedgerApi

PUBLIC_ID = PublicId.from_str("valory/donation_manager:0.1.0")

class DonationManagerContract(Contract):
    contract_id = PUBLIC_ID

    @classmethod
    def get_raw_transaction(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> Optional[JSONLike]:
        """Get raw transaction."""
        raise NotImplementedError

    @classmethod
    def get_raw_message(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> Optional[bytes]:
        """Get raw message."""
        raise NotImplementedError

    @classmethod
    def get_state(
        cls, ledger_api: LedgerApi, contract_address: str, **kwargs: Any
    ) -> Optional[JSONLike]:
        """Get state."""
        raise NotImplementedError

    @classmethod
    def donate(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        donor: str,
        amount: int
    ) -> Dict[str, Any]:
        contract_instance = cls.get_instance(ledger_api, contract_address)
        checksumed_donor = ledger_api.api.to_checksum_address(donor)
        tx_data = contract_instance.encodeABI(
            fn_name="donate",
            args=[checksumed_donor],
        )
        return dict(
            data=tx_data,
            value=amount
        )

    @classmethod
    def approve_donation_by_amount(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        admin: str,
        amount: int
    ) -> Dict[str, Any]:
        contract_instance = cls.get_instance(ledger_api, contract_address)
        checksumed_admin = ledger_api.api.to_checksum_address(admin)
        tx_data = contract_instance.encodeABI(
            fn_name="approveDonationByAmount",
            args=[amount],
        )
        return dict(
            data=tx_data,
            from=checksumed_admin
        )

    @classmethod
    def get_donations(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
    ) -> Dict[str, Any]:
        contract_instance = cls.get_instance(ledger_api, contract_address)
        donations = contract_instance.functions.getDonations().call()
        return dict(data=donations)
