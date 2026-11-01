import PropertiesAdmin from "./PropertiesAdmin";

/** Rental-only CRUD view over the shared property listing store. */
export default function RentalsAdmin() {
  return <PropertiesAdmin rentalOnly />;
}
