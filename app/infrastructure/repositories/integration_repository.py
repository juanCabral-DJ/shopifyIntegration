from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.integration import (
    EventInbox,
    EventOutbox,
    InventorySnapshot,
    MapClienteCustomer,
    MapFamiliasCollections,
    MapInvoices,
    MapMarcasTags,
    MapOrderIds,
    MapParametrosCache,
    MapProductImage,
    MapRecibos,
    MapSkuVariant,
    MapSucursalesLocations,
    SyncRun,
)


class IntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_inbox_event(
        self,
        source: str,
        topic: str,
        payload: dict[str, Any],
        external_id: str | None = None,
        status: str = "pending",
    ) -> EventInbox:
        event = EventInbox(
            source=source,
            topic=topic,
            external_id=external_id,
            payload=payload,
            status=status,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_inbox_done(self, event: EventInbox) -> EventInbox:
        event.status = "done"
        event.processed_at = datetime.now(timezone.utc)
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_inbox_failed(self, event: EventInbox, error: str) -> EventInbox:
        event.status = "failed"
        event.retry_count += 1
        event.error_message = error[:2000]
        self.session.add(event)
        await self.session.flush()
        return event

    async def add_outbox_event(
        self,
        target: str,
        operation: str,
        payload: dict[str, Any],
        status: str = "pending",
    ) -> EventOutbox:
        external_id = self._outbox_external_id(payload)
        if external_id:
            existing = await self.get_active_outbox_event(operation, external_id)
            if existing is not None:
                return existing
        event = EventOutbox(target=target, operation=operation, payload=payload, status=status)
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_active_outbox_event(self, operation: str, external_id: str) -> EventOutbox | None:
        result = await self.session.execute(
            select(EventOutbox)
            .where(EventOutbox.operation == operation)
            .where(EventOutbox.status.in_(("pending", "processing")))
        )
        for event in result.scalars().all():
            if self._outbox_external_id(event.payload) == external_id:
                return event
        return None

    async def list_due_outbox(self, limit: int = 50) -> list[EventOutbox]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(EventOutbox)
            .where(EventOutbox.status == "pending")
            .where(or_(EventOutbox.next_retry_at.is_(None), EventOutbox.next_retry_at <= now))
            .order_by(EventOutbox.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_outbox_processing(self, event: EventOutbox) -> EventOutbox:
        event.status = "processing"
        event.error_message = None
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_outbox_done(self, event: EventOutbox, response: Any | None = None) -> EventOutbox:
        event.status = "done"
        event.response = response
        event.error_message = None
        event.processed_at = datetime.now(timezone.utc)
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_outbox_failed(
        self,
        event: EventOutbox,
        error: str,
        max_retries: int = 5,
    ) -> EventOutbox:
        event.retry_count += 1
        event.error_message = error[:2000]
        if event.retry_count >= max_retries:
            event.status = "dead"
            event.next_retry_at = None
        else:
            event.status = "pending"
            event.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=min(2 ** event.retry_count * 30, 1800))
        self.session.add(event)
        await self.session.flush()
        return event

    async def reset_outbox_for_retry(self, shopify_order_id: int, operations: set[str]) -> EventOutbox | None:
        result = await self.session.execute(
            select(EventOutbox)
            .where(EventOutbox.operation.in_(operations))
            .where(EventOutbox.status.in_(("pending", "failed", "dead", "processing")))
            .order_by(EventOutbox.created_at.desc())
        )
        for event in result.scalars().all():
            payload = event.payload or {}
            if str(payload.get("shopify_order_id") or payload.get("id") or payload.get("order_id") or "") == str(shopify_order_id):
                event.status = "pending"
                event.retry_count = 0
                event.next_retry_at = None
                event.error_message = None
                self.session.add(event)
                await self.session.flush()
                return event
        return None

    async def list_inbox(self, status: str | None = None, limit: int = 100) -> list[EventInbox]:
        stmt = select(EventInbox).order_by(EventInbox.received_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(EventInbox.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_outbox(self, status: str | None = None, limit: int = 100) -> list[EventOutbox]:
        stmt = select(EventOutbox).order_by(EventOutbox.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(EventOutbox.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_order_map(self, shopify_order_id: int) -> MapOrderIds | None:
        result = await self.session.execute(
            select(MapOrderIds).where(MapOrderIds.shopify_order_id == shopify_order_id)
        )
        return result.scalars().first()

    async def upsert_order_map(
        self,
        shopify_order_id: int,
        shopify_order_name: str,
        factrx_movil_id: str | None = None,
        factrx_numero: str | None = None,
        status: str = "created",
    ) -> MapOrderIds:
        mapping = await self.get_order_map(shopify_order_id)
        if mapping is None:
            mapping = MapOrderIds(
                shopify_order_id=shopify_order_id,
                shopify_order_name=shopify_order_name,
                factrx_movil_id=factrx_movil_id,
                factrx_numero=factrx_numero,
                status=status,
            )
        else:
            mapping.shopify_order_name = shopify_order_name
            mapping.factrx_movil_id = factrx_movil_id
            mapping.factrx_numero = factrx_numero or mapping.factrx_numero
            mapping.status = status
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def upsert_invoice_map(
        self,
        shopify_order_id: int,
        factrx_numero: str,
        status: str = "invoiced",
        payload: dict[str, Any] | None = None,
        admncf_serial: str | None = None,
        ncf: str | None = None,
    ) -> MapInvoices:
        result = await self.session.execute(
            select(MapInvoices).where(
                and_(
                    MapInvoices.shopify_order_id == shopify_order_id,
                    MapInvoices.factrx_numero == factrx_numero,
                )
            )
        )
        mapping = result.scalars().first()
        if mapping is None:
            mapping = MapInvoices(shopify_order_id=shopify_order_id, factrx_numero=factrx_numero)
        mapping.status = status
        mapping.payload = payload or mapping.payload
        mapping.admncf_serial = admncf_serial or mapping.admncf_serial
        mapping.ncf = ncf or mapping.ncf
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def upsert_receipt_map(
        self,
        shopify_order_id: int,
        eftrcb_numero: int,
        amount: Any,
        currency: str | None = None,
        payment_source: str | None = None,
        reference: str | None = None,
        balance_pending: Any | None = None,
        status: str = "paid",
    ) -> MapRecibos:
        result = await self.session.execute(select(MapRecibos).where(MapRecibos.eftrcb_numero == eftrcb_numero))
        mapping = result.scalars().first()
        if mapping is None:
            mapping = MapRecibos(shopify_order_id=shopify_order_id, eftrcb_numero=eftrcb_numero, amount=amount)
        mapping.shopify_order_id = shopify_order_id
        mapping.amount = amount
        mapping.currency = currency or mapping.currency
        mapping.payment_source = payment_source or mapping.payment_source
        mapping.reference = reference or mapping.reference
        mapping.balance_pending = balance_pending
        mapping.status = status
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_sku_map_by_item_code(self, invitm_codigo: int) -> MapSkuVariant | None:
        result = await self.session.execute(
            select(MapSkuVariant).where(MapSkuVariant.invitm_codigo == invitm_codigo)
        )
        return result.scalars().first()

    async def get_sku_maps_by_item_codes(self, invitm_codigos: list[int]) -> dict[int, MapSkuVariant]:
        if not invitm_codigos:
            return {}
        result = await self.session.execute(
            select(MapSkuVariant).where(MapSkuVariant.invitm_codigo.in_(set(invitm_codigos)))
        )
        return {mapping.invitm_codigo: mapping for mapping in result.scalars().all()}

    async def get_sku_map_by_variant_id(self, shopify_variant_id: int) -> MapSkuVariant | None:
        result = await self.session.execute(
            select(MapSkuVariant).where(MapSkuVariant.shopify_variant_id == shopify_variant_id)
        )
        return result.scalars().first()

    async def get_sku_map_by_sku(self, sku: str) -> MapSkuVariant | None:
        result = await self.session.execute(select(MapSkuVariant).where(MapSkuVariant.sku == sku))
        return result.scalars().first()

    async def upsert_sku_map(
        self,
        invitm_codigo: int,
        sku: str,
        shopify_product_id: int | None = None,
        shopify_variant_id: int | None = None,
        shopify_inventory_item_id: int | None = None,
        last_price: Any | None = None,
        active: bool = True,
        existing_mapping: MapSkuVariant | None = None,
    ) -> MapSkuVariant:
        mapping = existing_mapping or await self.get_sku_map_by_item_code(invitm_codigo)
        if mapping is None:
            mapping = MapSkuVariant(invitm_codigo=invitm_codigo, sku=sku)
        mapping.sku = sku
        mapping.shopify_product_id = shopify_product_id or mapping.shopify_product_id
        mapping.shopify_variant_id = shopify_variant_id or mapping.shopify_variant_id
        mapping.shopify_inventory_item_id = shopify_inventory_item_id or mapping.shopify_inventory_item_id
        mapping.last_price = last_price if last_price is not None else mapping.last_price
        mapping.active = active
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_product_image_map(
        self,
        external_image_id: str,
        invitm_codigo: int | None = None,
        image_hash: str | None = None,
    ) -> MapProductImage | None:
        result = await self.session.execute(
            select(MapProductImage).where(MapProductImage.external_image_id == external_image_id)
        )
        mapping = result.scalars().first()
        if mapping is not None and (image_hash is None or mapping.image_hash == image_hash):
            return mapping
        if invitm_codigo is None or image_hash is None:
            return mapping
        result = await self.session.execute(
            select(MapProductImage).where(
                and_(
                    MapProductImage.invitm_codigo == invitm_codigo,
                    MapProductImage.image_hash == image_hash,
                )
            )
        )
        return result.scalars().first() or mapping

    async def upsert_product_image_map(
        self,
        external_image_id: str,
        invitm_codigo: int,
        image_hash: str,
        shopify_product_id: int,
        admimg_linea: int | None = None,
        shopify_image_id: int | None = None,
        filename: str | None = None,
    ) -> MapProductImage:
        mapping = await self.get_product_image_map(external_image_id, invitm_codigo, image_hash)
        if mapping is None:
            mapping = MapProductImage(
                external_image_id=external_image_id,
                invitm_codigo=invitm_codigo,
                image_hash=image_hash,
                shopify_product_id=shopify_product_id,
            )
        mapping.external_image_id = external_image_id
        mapping.invitm_codigo = invitm_codigo
        mapping.admimg_linea = admimg_linea
        mapping.image_hash = image_hash
        mapping.shopify_product_id = shopify_product_id
        mapping.shopify_image_id = shopify_image_id or mapping.shopify_image_id
        mapping.filename = filename or mapping.filename
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def upsert_customer_map(
        self,
        cxccte_codigo: int,
        shopify_customer_id: int | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> MapClienteCustomer:
        result = await self.session.execute(
            select(MapClienteCustomer).where(MapClienteCustomer.cxccte_codigo == cxccte_codigo)
        )
        mapping = result.scalars().first()
        if mapping is None:
            mapping = MapClienteCustomer(cxccte_codigo=cxccte_codigo)
        mapping.shopify_customer_id = shopify_customer_id or mapping.shopify_customer_id
        mapping.email = email or mapping.email
        mapping.phone = phone or mapping.phone
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_customer_map_by_shopify_id(self, shopify_customer_id: int) -> MapClienteCustomer | None:
        result = await self.session.execute(
            select(MapClienteCustomer).where(MapClienteCustomer.shopify_customer_id == shopify_customer_id)
        )
        return result.scalars().first()

    async def get_customer_map_by_email(self, email: str) -> MapClienteCustomer | None:
        result = await self.session.execute(select(MapClienteCustomer).where(MapClienteCustomer.email == email))
        return result.scalars().first()

    async def get_customer_map_by_phone(self, phone: str) -> MapClienteCustomer | None:
        result = await self.session.execute(select(MapClienteCustomer).where(MapClienteCustomer.phone == phone))
        return result.scalars().first()

    async def upsert_branch_map(
        self,
        admsuc_codigo: int,
        shopify_location_id: int | None = None,
        name: str | None = None,
        active: bool = True,
    ) -> MapSucursalesLocations:
        result = await self.session.execute(
            select(MapSucursalesLocations).where(MapSucursalesLocations.admsuc_codigo == admsuc_codigo)
        )
        mapping = result.scalars().first()
        if mapping is None:
            mapping = MapSucursalesLocations(admsuc_codigo=admsuc_codigo, shopify_location_id=shopify_location_id)
        mapping.shopify_location_id = shopify_location_id or mapping.shopify_location_id
        mapping.name = name or mapping.name
        mapping.active = active
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_branch_map_by_shopify_location_id(self, shopify_location_id: int) -> MapSucursalesLocations | None:
        result = await self.session.execute(
            select(MapSucursalesLocations).where(MapSucursalesLocations.shopify_location_id == shopify_location_id)
        )
        return result.scalars().first()

    async def get_branch_map_by_name(self, name: str) -> MapSucursalesLocations | None:
        normalized = name.strip().casefold()
        if not normalized:
            return None
        result = await self.session.execute(
            select(MapSucursalesLocations).where(func.lower(MapSucursalesLocations.name) == normalized)
        )
        return result.scalars().first()

    async def get_first_branch_map_with_location(self) -> MapSucursalesLocations | None:
        result = await self.session.execute(
            select(MapSucursalesLocations)
            .where(MapSucursalesLocations.shopify_location_id.is_not(None))
            .order_by(MapSucursalesLocations.admsuc_codigo)
        )
        return result.scalars().first()

    async def get_latest_inventory_with_stock(
        self,
        invitm_codigo: int,
        min_stock: Any = 1,
    ) -> InventorySnapshot | None:
        result = await self.session.execute(
            select(InventorySnapshot)
            .where(InventorySnapshot.invitm_codigo == invitm_codigo)
            .where(InventorySnapshot.admsuc_codigo.is_not(None))
            .where(InventorySnapshot.se_stock >= min_stock)
            .order_by(InventorySnapshot.captured_at.desc(), InventorySnapshot.se_stock.desc())
            .limit(1)
        )
        snapshot = result.scalars().first()
        if snapshot is not None:
            return snapshot

        result = await self.session.execute(
            select(InventorySnapshot)
            .where(InventorySnapshot.invitm_codigo == invitm_codigo)
            .where(InventorySnapshot.admsuc_codigo.is_not(None))
            .where(InventorySnapshot.se_stock > 0)
            .order_by(InventorySnapshot.captured_at.desc(), InventorySnapshot.se_stock.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def upsert_family_map(
        self,
        se_familia_id: str,
        se_familia_nombre: str | None = None,
        shopify_collection_id: int | None = None,
    ) -> MapFamiliasCollections:
        result = await self.session.execute(
            select(MapFamiliasCollections).where(MapFamiliasCollections.se_familia_id == se_familia_id)
        )
        mapping = result.scalars().first()
        if mapping is None and se_familia_nombre:
            normalized_name = se_familia_nombre.strip().lower()
            result = await self.session.execute(
                select(MapFamiliasCollections).where(
                    func.lower(func.trim(MapFamiliasCollections.se_familia_nombre)) == normalized_name
                )
            )
            mapping = result.scalars().first()
        if mapping is None and shopify_collection_id:
            result = await self.session.execute(
                select(MapFamiliasCollections).where(
                    MapFamiliasCollections.shopify_collection_id == shopify_collection_id
                )
            )
            mapping = result.scalars().first()
        if mapping is None:
            mapping = MapFamiliasCollections(se_familia_id=se_familia_id)
        mapping.se_familia_nombre = se_familia_nombre or mapping.se_familia_nombre
        mapping.shopify_collection_id = shopify_collection_id or mapping.shopify_collection_id
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def get_family_map_by_name(self, se_familia_nombre: str) -> MapFamiliasCollections | None:
        normalized_name = se_familia_nombre.strip().lower()
        if not normalized_name:
            return None
        result = await self.session.execute(
            select(MapFamiliasCollections).where(
                func.lower(func.trim(MapFamiliasCollections.se_familia_nombre)) == normalized_name
            )
        )
        return result.scalars().first()

    async def upsert_brand_map(
        self,
        se_marca_id: str,
        se_marca_nombre: str | None = None,
        shopify_tag: str | None = None,
    ) -> MapMarcasTags:
        result = await self.session.execute(
            select(MapMarcasTags).where(MapMarcasTags.se_marca_id == se_marca_id)
        )
        mapping = result.scalars().first()
        if mapping is None:
            mapping = MapMarcasTags(se_marca_id=se_marca_id, shopify_tag=shopify_tag or se_marca_nombre or se_marca_id)
        mapping.se_marca_nombre = se_marca_nombre or mapping.se_marca_nombre
        mapping.shopify_tag = shopify_tag or mapping.shopify_tag
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def add_inventory_snapshot(
        self,
        invitm_codigo: int,
        se_stock: Any,
        admsuc_codigo: int | None = None,
        mobile_physical_stock: Any | None = None,
        shopify_stock: Any | None = None,
        reconciled: bool = False,
        source_payload: dict[str, Any] | None = None,
    ) -> InventorySnapshot:
        snapshot = InventorySnapshot(
            invitm_codigo=invitm_codigo,
            admsuc_codigo=admsuc_codigo,
            se_stock=se_stock,
            mobile_physical_stock=mobile_physical_stock,
            shopify_stock=shopify_stock,
            reconciled=reconciled,
            source_payload=source_payload,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def set_param_cache(
        self,
        key: str,
        value: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> MapParametrosCache:
        cached = await self.session.get(MapParametrosCache, key)
        if cached is None:
            cached = MapParametrosCache(key=key, value=value, expires_at=expires_at)
        else:
            cached.value = value
            cached.expires_at = expires_at
        self.session.add(cached)
        await self.session.flush()
        return cached

    async def get_param_cache(self, key: str) -> MapParametrosCache | None:
        return await self.session.get(MapParametrosCache, key)

    async def start_sync_run(self, sync_type: str) -> SyncRun:
        run = SyncRun(sync_type=sync_type)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_sync_run(self, run_id: str) -> SyncRun | None:
        return await self.session.get(SyncRun, run_id)

    async def finish_sync_run(
        self,
        run: SyncRun,
        status: str,
        stats: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> SyncRun:
        run.status = status
        run.stats = stats
        run.error_message = error_message
        run.finished_at = datetime.now(timezone.utc)
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_sync_run_stats(self, run: SyncRun, stats: dict[str, Any]) -> SyncRun:
        run.stats = stats
        self.session.add(run)
        await self.session.flush()
        return run

    async def list_sync_runs(self, sync_type: str | None = None, limit: int = 50) -> list[SyncRun]:
        stmt = select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit)
        if sync_type:
            stmt = stmt.where(SyncRun.sync_type == sync_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_mapping(self, mapping: str, limit: int = 100) -> list[Any]:
        models = {
            "orders": MapOrderIds,
            "skus": MapSkuVariant,
            "customers": MapClienteCustomer,
            "invoices": MapInvoices,
            "receipts": MapRecibos,
            "product_images": MapProductImage,
            "branches": MapSucursalesLocations,
            "families": MapFamiliasCollections,
            "brands": MapMarcasTags,
            "params": MapParametrosCache,
            "inventory_snapshots": InventorySnapshot,
        }
        model = models[mapping]
        result = await self.session.execute(select(model).limit(limit))
        return list(result.scalars().all())

    def _outbox_external_id(self, payload: dict[str, Any] | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("external_id", "shopify_order_id", "factrx_movil_id", "id", "order_id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None
