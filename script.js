const searchInput = document.getElementById("searchInput");
const searchType = document.getElementById("searchType");

let allData = [];
let currentPage = 1;
const rowsPerPage = 10;

searchType.addEventListener("change", () => {

    if(searchType.value === "medicine"){
        searchInput.placeholder = "Search Medicine...";
        document.getElementById("result").innerHTML = "";
        document.getElementById("searchInput").value = "";
    }
    else{
        searchInput.placeholder = "Search Composition (e.g. Paracetamol 500 mg)";
        document.getElementById("result").innerHTML = "";
        document.getElementById("searchInput").value = "";
    }

});

async function searchMedicine(){

    const query = document.getElementById('searchInput').value.trim();
    const searchType = document.getElementById('searchType').value;

    if(!query){
        document.getElementById("result").innerHTML = "";
        return;
    }

    const response = await fetch(
        `http://127.0.0.1:8000/search?q=${encodeURIComponent(query)}&search_type=${searchType}`
    );

    const data = await response.json();

    allData = data;
    currentPage = 1;

    renderResult();
}


function renderResult(){

    const res = document.getElementById('result');

    if(allData.length === 0){
        res.innerHTML = `
            <div>
                <p> No result found. </p>
            </div>
        `;
        return;
    }

    // Pagination calculation
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;

    const paginatedData = allData.slice(start, end);

    let tableHTML = `
        <table>
            <thead>
                <tr>
                    <th> Medicine Name </th>
                    <th> Composition Name </th>
                    <th> Dosage Form </th>
                    <th> Manufacturer Name </th>
                    <th> Prescription Required </th>
                    <th> NPPA Regulated </th>
                    <th> Price </th>
                    <th> Pack Size </th>
                </tr>
            </thead>
            <tbody id="medicineTableBody">
    `;

    paginatedData.forEach(element => {

        let formattedPackSize = "-";

        if(element.pack_display){

            const parts = element.pack_display.split(" ");

            if(parts.length >= 2){

                const qty = parseFloat(parts[0]);
                const unit = parts.slice(1).join(" ");

                if(!isNaN(qty)){
                    formattedPackSize = `${qty.toFixed(2)} ${unit}`;
                }
                else{
                    formattedPackSize = element.pack_display;
                }
            }
            else{
                formattedPackSize = element.pack_display;
            }
        }

        tableHTML += `
            <tr id="row-${element.medicine_id}" onclick="loadAlternatives(${element.medicine_id})">
                <td> ${element.brand_name} </td>
                <td> ${element.composition} </td>
                <td> ${element.dosage_form} </td>
                <td> ${element.manufacturer} </td>
                <td> ${element.prescription_required ? "Yes" : "No"} </td>
                <td> ${element.nppa_regulated ? "Yes" : "No"} </td>
                <td> ₹${element.min_pack_mrp} </td>
                <td> ${formattedPackSize} </td>
            </tr>
        `;
    });

    tableHTML += `
        </tbody>
    </table>
    `;

    // Pagination buttons
    const totalPages = Math.ceil(allData.length / rowsPerPage);

    tableHTML += `
        <div class="pagination">

            <button
                onclick="changePage(${currentPage - 1})"
                ${currentPage === 1 ? "disabled" : ""}>
                Previous
            </button>

            <span> 
                Page ${currentPage} of ${totalPages} 
            </span>

            <button
                onclick="changePage(${currentPage + 1})"
                ${currentPage === totalPages ? "disabled" : ""}>
                Next
            </button>

        </div>
    `;

    res.innerHTML = tableHTML;
}


function changePage(page){

    const totalPages = Math.ceil(allData.length / rowsPerPage);

    if(page < 1 || page > totalPages){
        return;
    }

    currentPage = page;

    renderResult();
}


// Find Alternatives
async function loadAlternatives(medicineId){

    const currentRow = document.getElementById(`row-${medicineId}`);

    // Check if already opened
    const nextRow = currentRow.nextElementSibling;

    if(nextRow && nextRow.classList.contains("comparison-row")){
        nextRow.remove();
        return;
    }

    // Remove previous opened comparison
    document.querySelectorAll(".comparison-row").forEach(row => {
        row.remove();
    });

    // Create loading row
    const loadingRow = document.createElement("tr");

    loadingRow.className = "comparison-row";

    loadingRow.innerHTML = `
        <td colspan="8" style="text-align:center;">
            Loading alternatives...
        </td>
    `;

    currentRow.insertAdjacentElement("afterend", loadingRow);

    try{

        const response = await fetch(`http://127.0.0.1:8000/alternatives/${medicineId}`);

        const data = await response.json();

        let comparisonHTML = `
            <td colspan="8">
                <div class="comparison-wrapper">
                    <h2>Medicine Comparison</h2>
                    <table class="comparison-table">
                        <thead>
                            <tr>
                                <th>Medicine</th>
                                <th>Composition</th>
                                <th>Manufacturer</th>
                                <th>Dosage Form</th>
                                <th>Price</th>
                                <th>You Save</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        // Original medicine
        comparisonHTML += `
            <tr class="original-row">
                <td>${data.original.brand_name}</td>
                <td>${data.original.composition}</td>
                <td>${data.original.manufacturer}</td>
                <td>${data.original.dosage_form}</td>
                <td>₹${data.original.min_pack_mrp}</td>
                <td>-</td>
            </tr>
        `;

        // Alternatives
        data.alternatives.forEach(item => {

            const save = (data.original.min_pack_mrp - item.min_pack_mrp).toFixed(2);

            comparisonHTML += `
                <tr>
                    <td>${item.brand_name}</td>
                    <td>${item.composition}</td>
                    <td>${item.manufacturer}</td>
                    <td>${item.dosage_form}</td>
                    <td>₹${item.min_pack_mrp}</td>
                    <td style="color:green;">₹${save}</td>
                </tr>
            `;
        });

        comparisonHTML += `
                        </tbody>
                    </table>
                </div>
            </td>
        `;

        loadingRow.innerHTML = comparisonHTML;
    }

    catch(error){
        loadingRow.innerHTML = `
            <td colspan="8" style="color:red; text-align:center;">
                Failed to load alternatives
            </td>
        `;
    }
}



/* 
<tr onclick="window.location.href='alternatives.html?medicineId=${element.medicine_id}&mrp=${element.min_pack_mrp}'"> 
*/