package com.itguy.assetmanager.ui.assets

import com.itguy.assetmanager.data.model.Asset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The predicate behind the assets list's filter.
 *
 * Worth a test rather than a read-through: the rules are easy to state and
 * easy to get subtly wrong. A filter that is not set must match everything,
 * several filters must all agree rather than any one of them, and the
 * comparison has to fold case -- a status stored as "Checked-Out" and a
 * filter offering "checked-out" are the same thing to the person holding the
 * phone.
 */
class AssetFiltersTest {

    private fun asset(
        name: String = "Laptop",
        type: String = "Laptop",
        status: String = "Available",
        location: String = "HQ",
        manufacturer: String = "Dell",
    ) = Asset(
        id = name, AssetTag = name, Name = name, Type = type,
        Status = status, Location = location, Manufacturer = manufacturer,
    )

    @Test
    fun `nothing set matches everything`() {
        val f = AssetFilters()
        assertTrue(f.isEmpty)
        assertEquals(0, f.activeCount)
        assertTrue(f.matches(asset()))
        assertTrue(f.matches(asset(type = "Monitor", status = "Retired")))
    }

    @Test
    fun `a blank value is not a filter`() {
        // the sheet stores null for "Any"; an empty string can arrive from
        // data that has the field blank, and must not narrow anything
        val f = AssetFilters(status = "", type = null)
        assertTrue(f.isEmpty)
        assertTrue(f.matches(asset(status = "Retired")))
    }

    @Test
    fun `one filter keeps only what it names`() {
        val f = AssetFilters(status = "Available")
        assertTrue(f.matches(asset(status = "Available")))
        assertFalse(f.matches(asset(status = "Checked-Out")))
        assertEquals(1, f.activeCount)
    }

    @Test
    fun `two filters both have to agree`() {
        val f = AssetFilters(type = "Laptop", location = "HQ")
        assertTrue(f.matches(asset(type = "Laptop", location = "HQ")))
        assertFalse(f.matches(asset(type = "Laptop", location = "Warehouse")))
        assertFalse(f.matches(asset(type = "Monitor", location = "HQ")))
        assertEquals(2, f.activeCount)
    }

    @Test
    fun `case does not matter`() {
        val f = AssetFilters(status = "checked-out", manufacturer = "dell")
        assertTrue(f.matches(asset(status = "Checked-Out", manufacturer = "Dell")))
    }

    @Test
    fun `a filter is an exact value, not a substring`() {
        // the search box is for "contains"; a filter picked from a list means
        // that entry and not another that happens to start the same way
        val f = AssetFilters(type = "Laptop")
        assertFalse(f.matches(asset(type = "Laptop Charger")))
    }

    @Test
    fun `an asset missing the field is filtered out, not in`() {
        val f = AssetFilters(location = "HQ")
        assertFalse(f.matches(asset(location = "")))
    }

    @Test
    fun `all four at once`() {
        val f = AssetFilters(
            status = "Available", type = "Laptop",
            location = "HQ", manufacturer = "Dell",
        )
        assertEquals(4, f.activeCount)
        assertTrue(f.matches(asset()))
        assertFalse(f.matches(asset(manufacturer = "HP")))
    }

    @Test
    fun `clearing one widens the result again`() {
        val narrow = AssetFilters(type = "Laptop", location = "Warehouse")
        val wider = narrow.copy(location = null)
        assertFalse(narrow.matches(asset(type = "Laptop", location = "HQ")))
        assertTrue(wider.matches(asset(type = "Laptop", location = "HQ")))
        assertEquals(1, wider.activeCount)
    }
}
